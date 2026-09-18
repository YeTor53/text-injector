import os
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import random
import math

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')

def generate_wood_texture(size=512):
    """生成木质纹理"""
    img = Image.new('RGB', (size, size), (210, 180, 140))  # 浅木色底色
    draw = ImageDraw.Draw(img)

    # 绘制年轮线条
    for i in range(1, 20):
        y = i * (size // 20)
        # 随机弯曲
        for x in range(0, size, 5):
            offset = int(random.uniform(-3, 3))
            draw.line((x, y + offset, x+5, y + offset), fill=(139, 69, 19), width=2)

    # 添加噪点（木纹细节）
    pixels = img.load()
    for x in range(size):
        for y in range(size):
            if random.random() < 0.02:
                r = pixels[x, y][0] + random.randint(-20, 20)
                g = pixels[x, y][1] + random.randint(-20, 20)
                b = pixels[x, y][2] + random.randint(-20, 20)
                pixels[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

    # 轻微模糊让线条柔和
    img = img.filter(ImageFilter.SMOOTH)
    return img

def generate_stone_texture(size=512):
    """生成石头纹理（花岗岩风格）"""
    img = Image.new('RGB', (size, size), (128, 128, 128))
    draw = ImageDraw.Draw(img)

    # 绘制随机斑点
    for _ in range(800):
        x = random.randint(0, size-1)
        y = random.randint(0, size-1)
        r = random.randint(0, 2)
        color = (random.randint(80, 120), random.randint(80, 120), random.randint(80, 120))
        draw.ellipse((x-r, y-r, x+r, y+r), fill=color)

    # 添加噪点
    pixels = img.load()
    for x in range(size):
        for y in range(size):
            if random.random() < 0.1:
                shift = random.randint(-15, 15)
                r = pixels[x, y][0] + shift
                g = pixels[x, y][1] + shift
                b = pixels[x, y][2] + shift
                pixels[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

    # 轻微模糊
    img = img.filter(ImageFilter.SMOOTH_MORE)
    return img

def generate_ice_texture(size=512):
    """生成冰材质纹理（透明感 + 裂纹）"""
    # 冰底色淡蓝，带半透（使用RGBA）
    img = Image.new('RGBA', (size, size), (180, 220, 255, 200))
    draw = ImageDraw.Draw(img)

    # 绘制裂纹（白色细线）
    for _ in range(60):
        start_x = random.randint(0, size)
        start_y = random.randint(0, size)
        end_x = start_x + random.randint(-40, 40)
        end_y = start_y + random.randint(-40, 40)
        draw.line((start_x, start_y, end_x, end_y), fill=(255, 255, 255, 180), width=2)

    # 添加亮点（高光）
    for _ in range(200):
        x = random.randint(0, size-1)
        y = random.randint(0, size-1)
        r = random.randint(1, 3)
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(255, 255, 255, 220))

    # 轻微模糊
    img = img.filter(ImageFilter.SMOOTH)
    return img

if __name__ == '__main__':
    wood = generate_wood_texture(512)
    wood.save(os.path.join(OUT_DIR, 'WoodTexture.png'))
    print("木头材质已保存: WoodTexture.png")

    stone = generate_stone_texture(512)
    stone.save(os.path.join(OUT_DIR, 'StoneTexture.png'))
    print("石头材质已保存: StoneTexture.png")

    ice = generate_ice_texture(512)
    ice.save(os.path.join(OUT_DIR, 'IceTexture.png'))
    print("冰材质已保存: IceTexture.png")