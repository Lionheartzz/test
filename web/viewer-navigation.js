import * as THREE from 'three';

// These directions come from the original Viewer fit() contract. In particular,
// front is -Y and the existing ISO is intentionally not a symmetric diagonal.
export const VIEW_DIRECTIONS = Object.freeze({
  top: [0, -.001, 1], bottom: [0, .001, -1],
  front: [0, -1, .001], back: [0, 1, .001],
  left: [-1, 0, .001], right: [1, 0, .001],
  iso: [1.1, -1.6, 1.1],
});

export const CORNER_VIEWS = Object.freeze(Object.fromEntries(
  [-1, 1].flatMap(x => [-1, 1].flatMap(y => [-1, 1].map(z =>
    [`corner-${x > 0 ? 'r' : 'l'}${y < 0 ? 'f' : 'b'}${z > 0 ? 't' : 'd'}`,
      [x * 1.1, y * 1.6, z * 1.1]]))),
));

export function viewDirection(key) {
  const values = VIEW_DIRECTIONS[key] || CORNER_VIEWS[key];
  return values ? new THREE.Vector3(...values).normalize() : null;
}

export function cameraSpan(camera, distance) {
  return camera.isOrthographicCamera
    ? (camera.top - camera.bottom) / camera.zoom
    : 2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / camera.zoom;
}

export function resizeCamera(camera, width, height, orthoSpan) {
  if (width <= 0 || height <= 0) return false;
  const aspect = width / height;
  if (camera.isPerspectiveCamera) camera.aspect = aspect;
  else {
    const half = orthoSpan / 2;
    camera.left = -half * aspect;
    camera.right = half * aspect;
    camera.top = half;
    camera.bottom = -half;
  }
  camera.updateProjectionMatrix();
  return true;
}

export function frameCamera(camera, controls, bounds, width, height, padding = 1.12) {
  if (!bounds || bounds.isEmpty() || width <= 0 || height <= 0) return null;
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(bounds.getBoundingSphere(new THREE.Sphere()).radius, .5);
  const direction = camera.position.clone().sub(controls.target);
  if (direction.lengthSq() < 1e-12) direction.copy(viewDirection('iso'));
  direction.normalize();
  const aspect = width / height;
  let span = null;
  if (camera.isPerspectiveCamera) {
    const vertical = THREE.MathUtils.degToRad(camera.fov / 2);
    const limiting = Math.min(vertical, Math.atan(Math.tan(vertical) * aspect));
    const distance = radius / Math.sin(limiting) * padding * camera.zoom;
    camera.position.copy(center).addScaledVector(direction, distance);
    camera.near = .1;
    camera.far = Math.max(10000, distance + radius * 4);
  } else {
    span = 2 * radius * padding / Math.min(1, aspect);
    camera.zoom = 1;
    camera.position.copy(center).addScaledVector(direction, Math.max(radius * 3, 1));
    camera.near = .1;
    camera.far = Math.max(10000, radius * 8);
    resizeCamera(camera, width, height, span);
  }
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
  return span;
}
