from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
import json
import os
from io import BytesIO
from PIL import Image
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'cocktails.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'config.json')
WEB_IMAGES_DIR = os.path.join(BASE_DIR, 'static', 'web_images')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

cocktails_data = []
config = {}


def load_data():
    global cocktails_data
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        cocktails_data = json.load(f)


def save_data():
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cocktails_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def find_index(drink_id):
    for i, d in enumerate(cocktails_data):
        if d['id'] == drink_id:
            return i
    return -1


def load_config():
    global config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)


def save_config():
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_square(img, size=1080):
    """Resize image to size×size by cropping the longer side from center."""
    w, h = img.size
    if w == h == size:
        return img
    # Crop to square from center
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((size, size), Image.LANCZOS)
    return img


# ---- Frontend ----
@app.route('/')
def index():
    return render_template('index.html')


# ---- Admin ----
@app.route('/admin')
def admin():
    return render_template('admin.html')


# ---- API ----
@app.route('/api/cocktails', methods=['GET'])
def get_all():
    resp = make_response(jsonify(cocktails_data))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/api/cocktails/<drink_id>', methods=['GET'])
def get_one(drink_id):
    idx = find_index(drink_id)
    if idx == -1:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(cocktails_data[idx])


@app.route('/api/cocktails/<drink_id>', methods=['PUT'])
def update(drink_id):
    idx = find_index(drink_id)
    if idx == -1:
        return jsonify({'error': 'Not found'}), 404
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    cocktails_data[idx].update(data)
    # keep hasImg in sync with img
    cocktails_data[idx]['hasImg'] = bool(cocktails_data[idx].get('img', ''))
    save_data()
    return jsonify(cocktails_data[idx])


@app.route('/api/cocktails', methods=['POST'])
def create():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    # generate id if missing
    if 'id' not in data or not data['id']:
        import re
        slug = data['name'].lower().replace(' ', '_')
        data['id'] = re.sub(r'[^a-z0-9_-]', '', slug) or ('d' + str(len(cocktails_data)))
    # set defaults
    data.setdefault('en', '')
    data.setdefault('cat', '特调')
    data.setdefault('price', '¥96')
    data.setdefault('abv', '')
    data.setdefault('desc', '')
    data.setdefault('flavor', '')
    data.setdefault('spirit', '')
    data.setdefault('img', '')
    data.setdefault('hasImg', False)
    data.setdefault('note', '')
    cocktails_data.append(data)
    save_data()
    return jsonify(data), 201


@app.route('/api/cocktails/<drink_id>', methods=['DELETE'])
def delete(drink_id):
    idx = find_index(drink_id)
    if idx == -1:
        return jsonify({'error': 'Not found'}), 404
    deleted = cocktails_data.pop(idx)
    save_data()
    return jsonify(deleted), 200


@app.route('/api/upload/<drink_id>', methods=['POST'])
def upload(drink_id):
    idx = find_index(drink_id)
    if idx == -1:
        return jsonify({'error': 'Not found'}), 404
    if 'image' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['image']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    img = Image.open(BytesIO(file.read()))
    img = img.convert('RGB')
    img = resize_square(img, 1080)

    filename = secure_filename(f'{drink_id}.jpg')
    filepath = os.path.join(WEB_IMAGES_DIR, filename)
    img.save(filepath, 'JPEG', quality=85)

    cocktails_data[idx]['img'] = f'web_images/{filename}'
    cocktails_data[idx]['hasImg'] = True
    save_data()
    return jsonify(cocktails_data[idx])


# ---- Sync (commit via GitHub API) ----
@app.route('/api/sync', methods=['POST'])
def sync():
    import base64
    import urllib.request
    import urllib.error

    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return jsonify({'ok': False, 'msg': '未配置 GITHUB_TOKEN'}), 500

    REPO = 'Fiiionana/ontop-cocktail'
    API = f'https://api.github.com/repos/{REPO}/contents'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }

    files_to_sync = [
        'data/cocktails.json',
        'data/config.json',
    ]
    # Add all images in web_images
    for fname in os.listdir(WEB_IMAGES_DIR):
        if not fname.startswith('.'):
            files_to_sync.append(f'static/web_images/{fname}')

    synced = 0
    errors = []

    for rel_path in files_to_sync:
        local_path = os.path.join(BASE_DIR, rel_path)
        if not os.path.exists(local_path):
            continue
        with open(local_path, 'rb') as f:
            content = f.read()
        content_b64 = base64.b64encode(content).decode('utf-8')

        # Get remote SHA if file exists
        sha = None
        try:
            req = urllib.request.Request(f'{API}/{rel_path}', headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                sha = json.loads(resp.read()).get('sha')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                errors.append(f'{rel_path}: HTTP {e.code}')
                continue

        body = json.dumps({
            'message': 'Sync: upload from admin',
            'content': content_b64,
            'branch': 'main',
        } | ({'sha': sha} if sha else {}))
        body_bytes = body.encode('utf-8')

        try:
            req = urllib.request.Request(f'{API}/{rel_path}', data=body_bytes, headers=headers, method='PUT')
            urllib.request.urlopen(req, timeout=15)
            synced += 1
        except urllib.error.HTTPError as e:
            errors.append(f'{rel_path}: HTTP {e.code}')
        except Exception as e:
            errors.append(f'{rel_path}: {e}')

    if errors:
        return jsonify({'ok': False, 'msg': f'已同步 {synced} 个文件，{len(errors)} 个失败: {"; ".join(errors[:3])}'})
    return jsonify({'ok': True, 'msg': f'已同步 {synced} 个文件到 GitHub'})


# ---- Config API ----
@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(config)


@app.route('/api/config', methods=['PUT'])
def update_config():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    config.update(data)
    save_config()
    return jsonify(config)


# ---- Static fallback (for dev) ----
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static'), filename)


# ---- Init ----
os.makedirs(WEB_IMAGES_DIR, exist_ok=True)
load_data()
load_config()
print(f'Loaded {len(cocktails_data)} cocktails')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
