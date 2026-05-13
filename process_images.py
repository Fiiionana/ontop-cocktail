"""
One-shot: import images from 鸡尾酒图片/, remove white backgrounds, save to static/web_images/, update JSON.
"""
import json, os, shutil
from PIL import Image

SRC = os.path.join(os.path.dirname(__file__), '鸡尾酒图片')
DST = os.path.join(os.path.dirname(__file__), 'static', 'web_images')
JSON = os.path.join(os.path.dirname(__file__), 'data', 'cocktails.json')

# image filename (without _副本) → expected drink name
NAME_MAP = {
    '藤井树': '藤井树', '澪': '澪', '记念': '记念', '休假2.0': '休假2.0',
    '兰纳': '兰纳', '毒藤': '毒藤', '潮红': '潮红', 'R-16玛丽': 'R-16玛丽',
    '芫荽': '芫荽', '阿基拉': '阿基拉', '哥伦布斯': '哥伦布斯', '地平线': '地平线',
}


def remove_white_bg(img):
    """Convert white pixels to transparent, with smooth edge falloff."""
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


def main():
    os.makedirs(DST, exist_ok=True)

    with open(JSON, 'r', encoding='utf-8') as f:
        cocktails = json.load(f)

    updated = 0

    for fname in sorted(os.listdir(SRC)):
        if fname.startswith('.') or '_副本' not in fname:
            continue
        base = os.path.splitext(fname)[0]
        name = base.replace('_副本', '')
        ext = os.path.splitext(fname)[1].lower()
        src_path = os.path.join(SRC, fname)
        dst_name = name + '.png'
        dst_path = os.path.join(DST, dst_name)

        print(f'Processing: {fname} → {dst_name} ...', end=' ')

        img = Image.open(src_path)
        if ext in ('.jpg', '.jpeg'):
            img = remove_white_bg(img)
        img.save(dst_path, 'PNG')
        print(f'OK ({img.width}x{img.height})')

        # Update JSON
        img_path = 'web_images/' + dst_name
        for d in cocktails:
            if d['name'] == name:
                d['img'] = img_path
                d['hasImg'] = True
                updated += 1
                print(f'  → Updated JSON: {d["name"]} ({d["id"]})')
                break
        else:
            print(f'  ⚠ No matching drink found for "{name}"')

    with open(JSON, 'w', encoding='utf-8') as f:
        json.dump(cocktails, f, ensure_ascii=False, indent=2)

    print(f'\nDone. {updated} drinks updated in cocktails.json')


if __name__ == '__main__':
    main()
