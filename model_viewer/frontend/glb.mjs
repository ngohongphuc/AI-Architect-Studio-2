// Đọc tệp GLB do tools/model3d.py tạo (không texture, không nén, accessor liền khối).
const ARRAYS = {5126: Float32Array, 5125: Uint32Array};
const SIZES = {SCALAR: 1, VEC3: 3};

export function parseGlb(buffer) {
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x46546c67 || view.getUint32(8, true) !== buffer.byteLength) {
    throw new Error("Tệp GLB không hợp lệ.");
  }
  const jsonLength = view.getUint32(12, true);
  const doc = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, jsonLength)));
  const start = 20 + jsonLength + 8;
  const read = (index) => {
    const {bufferView, componentType, count, type} = doc.accessors[index];
    const {byteOffset} = doc.bufferViews[bufferView];
    return new ARRAYS[componentType](buffer, start + byteOffset, count * SIZES[type]);
  };
  const parts = doc.nodes.filter((node) => node.mesh !== undefined).map((node) => ({
    name: node.name,
    group: node.extras.group,
    primitives: doc.meshes[node.mesh].primitives.map((item) => ({
      position: read(item.attributes.POSITION),
      normal: read(item.attributes.NORMAL),
      index: read(item.indices),
      material: doc.materials[item.material],
    })),
  }));
  return {parts, floors: doc.asset.extras.so_tang, stamp: doc.asset.extras.AI_ARCHITECT_OPTION};
}
