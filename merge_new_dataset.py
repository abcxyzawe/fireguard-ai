"""
Merge NEWFireSmokeDataset vao dataset_v2 de tao dataset_v3.
Remap labels: NEWFireSmokeDataset dung 0=fire, 1=other, 2=smoke
              He thong dung 0=smoke, 1=fire
              -> fire(0)->1, smoke(2)->0, other(1)->bo qua (hoac dung lam background)
"""
import os, shutil, glob

SRC_DATASETS = [
    'dataset_new_tmp/data/yolov8_dataset1',
    'dataset_new_tmp/data/yolov8_dataset2',
]
DST = 'dataset_v3'

# Copy dataset_v2 as base
if not os.path.exists(DST):
    print("Copying dataset_v2 as base...")
    shutil.copytree('dataset_v2', DST)
else:
    print(f"{DST} already exists, merging into it...")

# Remap and merge
CLASS_REMAP = {0: 1, 2: 0}  # fire->1, smoke->0, other(1)->skip

total_added = 0
for ds_path in SRC_DATASETS:
    ds_name = os.path.basename(ds_path)
    for split_src, split_dst in [('train', 'train'), ('valid', 'val'), ('test', 'test')]:
        img_dir = os.path.join(ds_path, split_src, 'images')
        lbl_dir = os.path.join(ds_path, split_src, 'labels')

        if not os.path.exists(img_dir):
            continue

        imgs = glob.glob(os.path.join(img_dir, '*'))
        count = 0
        for img_path in imgs:
            bn = os.path.basename(img_path)
            name_no_ext = bn.rsplit('.', 1)[0]
            ext = bn.rsplit('.', 1)[-1]

            # New name with prefix to avoid collision
            new_img_name = f'new_{ds_name}_{bn}'
            new_lbl_name = f'new_{ds_name}_{name_no_ext}.txt'

            dst_img = os.path.join(DST, split_dst, 'images', new_img_name)
            dst_lbl = os.path.join(DST, split_dst, 'labels', new_lbl_name)

            if os.path.exists(dst_img):
                continue

            # Remap label
            src_lbl = os.path.join(lbl_dir, f'{name_no_ext}.txt')
            new_lines = []
            if os.path.exists(src_lbl):
                with open(src_lbl) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            cls = int(parts[0])
                            if cls in CLASS_REMAP:
                                parts[0] = str(CLASS_REMAP[cls])
                                new_lines.append(' '.join(parts))
                            # cls=1 (other) -> skip this bbox

            # Copy image
            shutil.copy2(img_path, dst_img)

            # Write remapped label (empty = background/negative)
            with open(dst_lbl, 'w') as f:
                if new_lines:
                    f.write('\n'.join(new_lines) + '\n')

            count += 1

        total_added += count
        print(f'{ds_name}/{split_src} -> {split_dst}: added {count} images')

# Final count
for split in ['train', 'val', 'test']:
    imgs = len(os.listdir(os.path.join(DST, split, 'images')))
    lbls = len(os.listdir(os.path.join(DST, split, 'labels')))
    print(f'{split}: {imgs} images, {lbls} labels')

print(f'\nTotal added: {total_added}')
print('Done!')

# Write data.yaml
yaml_path = os.path.join(DST, 'data.yaml')
with open(yaml_path, 'w') as f:
    f.write(f"""# Dataset v3 - Indoor Fire/Smoke + NEWFireSmokeDataset
# D-Fire + Indoor + Auto + NEWFireSmoke (with hard negatives)

path: E:/Kiem_soat_lua/{DST}

train: train/images
val: val/images
test: test/images

nc: 2
names: ["smoke", "fire"]
""")
print(f'data.yaml written to {yaml_path}')
