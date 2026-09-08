import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

export function createViewer(container, onSelect) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 10000);
  camera.up.set(0, 0, 1);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0, 0);
  container.append(renderer.domElement);
  const labels = new CSS2DRenderer();
  Object.assign(labels.domElement.style, { position: 'absolute', top: '0', pointerEvents: 'none' });
  container.append(labels.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  scene.add(new THREE.HemisphereLight(0xe8f4ff, 0x526478, 2.6));
  for (const [position, intensity] of [[[100, -200, 400], 3], [[-200, 200, 180], 1.8]]) {
    const light = new THREE.DirectionalLight(0xffffff, intensity);
    light.position.set(...position); scene.add(light);
  }
  let group = new THREE.Group(), labelGroup = new THREE.Group(), grid;
  scene.add(group, labelGroup);
  let block, mode = 'review', opacity = .22, selected = 'block';
  const visible = { cavities: true, drillings: true, labels: true, circuits: new Set(['P', 'T', 'A', 'B', 'LS', 'Drain']) };
  function disposeGroup(target) {
    target.traverse(o => { o.geometry?.dispose(); if (o.material) o.material.dispose(); if (o.element) o.element.remove(); });
    target.clear();
  }
  function fit(view = 'iso') {
    if (!block) return;
    const center = new THREE.Vector3(block.length / 2, block.width / 2, block.height / 2);
    const radius = Math.hypot(block.length, block.width, block.height) / 2;
    const halfFov = Math.min(THREE.MathUtils.degToRad(camera.fov / 2), Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
    const distance = radius / Math.sin(halfFov) * 1.12;
    const dir = view === 'top' ? new THREE.Vector3(0, -.001, 1) : new THREE.Vector3(1.1, -1.6, 1.1).normalize();
    camera.position.copy(center).addScaledVector(dir, distance);
    controls.target.copy(center); camera.near = .1; camera.far = Math.max(10000, distance * 5);
    camera.updateProjectionMatrix(); controls.update();
  }
  function updateVisibility() {
    group.children.forEach(o => {
      const p = o.userData;
      o.visible = p.kind === 'body' || p.kind === 'edge' || (mode === 'review'
        && (!(p.kind === 'cavity' || p.kind === 'zone') || visible.cavities)
        && (!(p.kind === 'drilling' || p.kind === 'plug') || visible.drillings)
        && (!p.circuit || visible.circuits.has(p.circuit)));
      if (p.kind === 'body') { o.material.opacity = mode === 'solid' ? 1 : opacity; o.material.depthWrite = mode === 'solid' || opacity >= .99; }
    });
    labelGroup.children.forEach(o => {
      const p = o.userData;
      o.visible = visible.labels && (p.kind !== 'cavity' || visible.cavities) && (p.kind !== 'drilling' || visible.drillings)
        && (!p.circuit || visible.circuits.has(p.circuit));
    });
  }
  function select(id) {
    selected = id;
    group.children.forEach(o => {
      if (o.material?.emissive) o.material.emissive.set(o.userData.owner === id && id !== 'block' ? '#425948' : '#000000');
    });
  }
  function load(model, features) {
    const first = !block; block = model.block;
    disposeGroup(group); disposeGroup(labelGroup);
    if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
    grid = new THREE.GridHelper(Math.max(block.length, block.width) * 2.8, 28, 0x3d5266, 0x2a394b);
    grid.rotation.x = Math.PI / 2; grid.position.set(block.length / 2, block.width / 2, -.5); scene.add(grid);
    for (const p of model.parts) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(p.vertices, 3)); geo.setIndex(p.triangles); geo.computeVertexNormals();
      const transparent = p.kind === 'body' || p.kind === 'cavity';
      const material = new THREE.MeshStandardMaterial({ color: p.color, metalness: p.kind === 'body' ? .35 : .12,
        roughness: .42, transparent, opacity: p.kind === 'body' ? opacity : p.kind === 'cavity' ? .13 : 1,
        depthWrite: !transparent, side: THREE.FrontSide });
      const object = new THREE.Mesh(geo, material); object.userData = p;
      object.renderOrder = p.kind === 'body' ? 3 : p.kind === 'cavity' ? 2 : 0;
      group.add(object);
      if (p.kind === 'body') {
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: '#8197ad', transparent: true, opacity: .25 }));
        edges.userData = { kind: 'edge' }; group.add(edges);
      }
    }
    for (const f of features) {
      const pose = model.placements[f.id]; if (!pose) continue;
      // A coaxial gallery and external port share a mouth; label the port once.
      if (f.kind === 'drilling' && !f.plugged && features.some(p => p.kind === 'port' && p.face === f.face && p.u === f.u && p.v === f.v)) continue;
      const element = document.createElement('div'); element.className = 'model-label'; element.textContent = f.id + (f.plugged ? ' · PLUG' : '');
      const label = new CSS2DObject(element); label.position.set(...pose.origin).addScaledVector(new THREE.Vector3(...pose.direction), -8);
      label.userData = f; labelGroup.add(label);
    }
    updateVisibility(); select(selected); if (first) fit();
  }
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let down;
  renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || e.button !== 0) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1);
    ray.setFromCamera(pointer, camera);
    const candidates = group.children.filter(o => o.isMesh && o.visible && (mode === 'solid' || o.userData.kind !== 'body'));
    const hit = ray.intersectObjects(candidates)[0];
    onSelect(hit ? hit.object.userData.owner || 'block' : 'block');
  });
  const resize = new ResizeObserver(() => {
    const w = container.clientWidth, h = container.clientHeight;
    camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h); labels.setSize(w, h);
  });
  resize.observe(container);
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); labels.render(scene, camera); });
  return { load, fit, select, mode(value) { mode = value; updateVisibility(); }, opacity(value) { opacity = value; updateVisibility(); },
    toggle(key, value) { visible[key] = value; updateVisibility(); }, circuit(id, show) { show ? visible.circuits.add(id) : visible.circuits.delete(id); updateVisibility(); } };
}
