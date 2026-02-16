import React, { useRef, useEffect, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { getCadUrl } from '../../utils/cadApi';
import api from '../../services/api';

const DEFAULT_SCENE_CONFIG = {
  name: 'Default',
  camera: { position: [50, 50, 50], target: [0, 0, 0] },
  background: '#1a1a2e',
  lights: [
    { type: 'ambient', color: '#404040', intensity: 0.4 },
    { type: 'directional', color: '#ffffff', intensity: 0.8, position: [50, 50, 50] },
    { type: 'directional', color: '#6699ff', intensity: 0.3, position: [-30, -20, 30] },
    { type: 'directional', color: '#ffaa66', intensity: 0.4, position: [0, 30, -50] },
    { type: 'hemisphere', skyColor: '#87ceeb', groundColor: '#444444', intensity: 0.5 },
  ],
};

function hexToThreeColor(hex) {
  if (!hex) return 0x58a6ff;
  const c = String(hex).replace('#', '');
  return parseInt(c.length >= 6 ? c.slice(0, 6) : '58a6ff', 16);
}

function createLightFromSpec(spec, lightsRef) {
  const color = (c) => (typeof c === 'string' ? hexToThreeColor(c) : c);
  if (spec.type === 'ambient') {
    return new THREE.AmbientLight(color(spec.color), spec.intensity ?? 0.4);
  }
  if (spec.type === 'directional') {
    const L = new THREE.DirectionalLight(color(spec.color), spec.intensity ?? 0.8);
    if (spec.position) L.position.set(spec.position[0], spec.position[1], spec.position[2]);
    return L;
  }
  if (spec.type === 'hemisphere') {
    return new THREE.HemisphereLight(
      color(spec.skyColor ?? '#87ceeb'),
      color(spec.groundColor ?? '#444444'),
      spec.intensity ?? 0.5
    );
  }
  return null;
}

function computeBoxProjectionUVs(geometry) {
  const pos = geometry.attributes.position;
  if (!pos) return;
  const bbox = new THREE.Box3().setFromBufferAttribute(pos);
  const size = new THREE.Vector3();
  bbox.getSize(size);
  const center = new THREE.Vector3();
  bbox.getCenter(center);
  const eps = 1e-6;
  size.x = Math.max(size.x, eps);
  size.y = Math.max(size.y, eps);
  size.z = Math.max(size.z, eps);
  const uvs = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i) - center.x;
    const y = pos.getY(i) - center.y;
    const z = pos.getZ(i) - center.z;
    const ax = Math.abs(x);
    const ay = Math.abs(y);
    const az = Math.abs(z);
    let u, v;
    if (ax >= ay && ax >= az) {
      u = (z / size.z + 1) * 0.5;
      v = (y / size.y + 1) * 0.5;
      if (x < 0) u = 1 - u;
    } else if (ay >= ax && ay >= az) {
      u = (x / size.x + 1) * 0.5;
      v = (z / size.z + 1) * 0.5;
      if (y < 0) u = 1 - u;
    } else {
      u = (x / size.x + 1) * 0.5;
      v = (y / size.y + 1) * 0.5;
      if (z < 0) u = 1 - u;
    }
    uvs[i * 2] = u;
    uvs[i * 2 + 1] = v;
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
}

export default function CadViewer({
  geometryUrl,
  format,
  meshes,
  sceneConfig,
  showAxes,
  centerModel,
  lightsState,
  onLightsChange,
}) {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const controlsRef = useRef(null);
  const axesRef = useRef(null);
  const lightsRef = useRef({});
  const lastLoadRef = useRef({ center: null, maxDim: 1, model: null, meshPositions: null });
  const lastGeometryUrlBaseRef = useRef(null);

  const resize = useCallback(() => {
    const renderer = rendererRef.current;
    const camera = cameraRef.current;
    const container = containerRef.current;
    if (!renderer || !camera || !container) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w > 0 && h > 0) {
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);
    sceneRef.current = scene;

    const w = Math.max(container.clientWidth || 640, 1);
    const h = Math.max(container.clientHeight || 480, 1);
    const camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000);
    camera.position.set(50, 50, 50);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const config = sceneConfig || DEFAULT_SCENE_CONFIG;
    const lightKeys = ['ambient', 'key', 'fill', 'back', 'hemi'];
    const defaultSpecs = DEFAULT_SCENE_CONFIG.lights;
    lightKeys.forEach((key, i) => {
      const spec = config.lights?.[i] || defaultSpecs[i];
      const L = spec ? createLightFromSpec(spec, lightsRef) : null;
      if (L) {
        lightsRef.current[key] = L;
        scene.add(L);
      }
    });

    const axesGroup = new THREE.Group();
    const axesHelper = new THREE.AxesHelper(30);
    axesGroup.add(axesHelper);
    scene.add(axesGroup);
    axesRef.current = axesGroup;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    if (config.background) scene.background = new THREE.Color(config.background);
    if (config.camera?.position) camera.position.set(...config.camera.position);
    if (config.camera?.target) controls.target.set(...config.camera.target);

    const animate = () => {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    window.addEventListener('resize', resize);

    return () => {
      window.removeEventListener('resize', resize);
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    if (axesRef.current) axesRef.current.visible = showAxes;
  }, [showAxes]);

  useEffect(() => {
    const lights = lightsRef.current;
    if (!lightsState || !lights.ambient) return;
    ['ambient', 'key', 'fill', 'back', 'hemi'].forEach((key, i) => {
      if (lights[key] && lightsState[i] != null) lights[key].intensity = lightsState[i];
    });
  }, [lightsState]);

  const loadGeometry = useCallback(async () => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const axesGroup = axesRef.current;
    if (!scene || !camera || !controls) return;

    scene.children.filter((c) => (c.isMesh || c.isGroup) && c !== axesGroup).forEach((c) => scene.remove(c));
    lastLoadRef.current = { center: null, maxDim: 1, model: null, meshPositions: null };

    if (!geometryUrl && (!meshes || meshes.length === 0)) {
      onLightsChange?.({ loaded: false });
      lastGeometryUrlBaseRef.current = null;
      return;
    }

    const urlBase = geometryUrl ? geometryUrl.split('?')[0] : (meshes?.[0]?.url?.split('?')[0] ?? '');
    const preserveCamera = lastGeometryUrlBaseRef.current !== null && lastGeometryUrlBaseRef.current === urlBase;

    const finishLoad = (center, maxDim, model, meshPositions, keepCamera = false) => {
      lastLoadRef.current = { center, maxDim, model, meshPositions };
      lastGeometryUrlBaseRef.current = urlBase;
      const doCenter = centerModel ?? true;
      if (meshPositions) {
        meshPositions.forEach((m) => (doCenter ? m.position.sub(center) : m.position.set(0, 0, 0)));
      } else if (model) {
        doCenter ? model.position.sub(center) : model.position.set(0, 0, 0);
      }
      if (!keepCamera) {
        controls.target.set(doCenter ? 0 : center.x, doCenter ? 0 : center.y, doCenter ? 0 : center.z);
        camera.position.set(center.x + maxDim, center.y + maxDim, center.z + maxDim);
        camera.lookAt(doCenter ? 0 : center.x, doCenter ? 0 : center.y, doCenter ? 0 : center.z);
      }
      if (axesGroup) axesGroup.position.set(0, 0, 0);
      onLightsChange?.({ loaded: true });
    };

    try {
      if (format === 'glb' || (geometryUrl && (geometryUrl.includes('.glb') || geometryUrl.includes('/geometry')))) {
        const url = geometryUrl.startsWith('http') ? geometryUrl : getCadUrl(geometryUrl);
        const res = await api.fetch(url);
        if (!res.ok) throw new Error('Failed to load geometry');
        const arrayBuffer = await res.arrayBuffer();
        const loader = new GLTFLoader();
        const gltf = await new Promise((resolve, reject) => {
          loader.parse(arrayBuffer, '', resolve, reject);
        });
        const model = gltf.scene;
        scene.add(model);
        const bbox = new THREE.Box3().setFromObject(model);
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        const size = bbox.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 1);
        finishLoad(center, maxDim, model, null, preserveCamera);
      } else if (meshes && meshes.length > 0) {
        const loader = new STLLoader();
        const loadedMeshes = [];
        for (const item of meshes) {
          const url = item.url.startsWith('http') ? item.url : getCadUrl(item.url);
          const res = await api.fetch(url);
          if (!res.ok) throw new Error('Failed to load mesh');
          const arrayBuffer = await res.arrayBuffer();
          const geometry = loader.parse(arrayBuffer);
          geometry.computeVertexNormals();
          if (!geometry.attributes.uv) computeBoxProjectionUVs(geometry);
          const color = hexToThreeColor(item.color || '#58a6ff');
          const mat = new THREE.MeshPhongMaterial({
            color,
            specular: hexToThreeColor(item.specular ?? '#111111'),
            shininess: item.shininess ?? 100,
          });
          const mesh = new THREE.Mesh(geometry, mat);
          scene.add(mesh);
          loadedMeshes.push(mesh);
        }
        const bbox = new THREE.Box3();
        loadedMeshes.forEach((m) => bbox.expandByObject(m));
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        const size = bbox.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 1);
        finishLoad(center, maxDim, null, loadedMeshes, preserveCamera);
      } else if (geometryUrl) {
        const url = geometryUrl.startsWith('http') ? geometryUrl : getCadUrl(geometryUrl);
        const res = await api.fetch(url);
        if (!res.ok) throw new Error('Failed to load geometry');
        const arrayBuffer = await res.arrayBuffer();
        const loader = new STLLoader();
        const geometry = loader.parse(arrayBuffer);
        geometry.computeVertexNormals();
        if (!geometry.attributes.uv) computeBoxProjectionUVs(geometry);
        const mesh = new THREE.Mesh(geometry, new THREE.MeshPhongMaterial({ color: 0x58a6ff }));
        scene.add(mesh);
        const bbox = new THREE.Box3().setFromObject(mesh);
        const center = new THREE.Vector3();
        bbox.getCenter(center);
        const size = bbox.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 1);
        finishLoad(center, maxDim, mesh, null, preserveCamera);
      }
    } catch (err) {
      console.error('Failed to load geometry', err);
      onLightsChange?.({ loaded: false, error: err.message });
    }
  }, [geometryUrl, format, meshes, centerModel, onLightsChange]);

  useEffect(() => {
    loadGeometry();
  }, [loadGeometry]);

  return <div ref={containerRef} className="w-full h-full min-h-[400px] bg-[#1a1a2e]" />;
}
