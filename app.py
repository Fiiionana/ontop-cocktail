from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
from io import BytesIO
from PIL import Image
from werkzeug.utils import secure_filename

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'cocktails.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'config.json')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
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


def remove_white_bg(img):
    """Convert white/near-white pixels to transparent, preserving edges."""
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r > 240 and g > 240 and b > 240:
                whiteness = (r + g + b) / 3
                alpha = max(0, int(255 - (whiteness - 235) * 12))
                pixels[x, y] = (r, g, b, min(a, alpha))
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
    return jsonify(cocktails_data)


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

    ext = file.filename.rsplit('.', 1)[1].lower()
    original_bytes = file.read()

    # Auto-process: JPG/JPEG → remove white bg → save as PNG
    if ext in ('jpg', 'jpeg'):
        img = Image.open(BytesIO(original_bytes))
        img = remove_white_bg(img)
        save_ext = 'png'
        out_bytes = BytesIO()
        img.save(out_bytes, 'PNG')
        out_bytes.seek(0)
    else:
        save_ext = ext
        out_bytes = BytesIO(original_bytes)

    filename = secure_filename(f'{drink_id}.{save_ext}')
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, 'wb') as f:
        f.write(out_bytes.read())

    cocktails_data[idx]['img'] = f'uploads/{filename}'
    cocktails_data[idx]['hasImg'] = True
    save_data()
    return jsonify(cocktails_data[idx])


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
os.makedirs(UPLOAD_DIR, exist_ok=True)
load_data()
load_config()
print(f'Loaded {len(cocktails_data)} cocktails')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
