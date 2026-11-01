/**
 * Kazama Protocol - True 3D Neural Constellation & Singularity Engine
 * Features:
 * - Genuine 3D PBR Spheres with Specular Shading & Depth
 * - Smooth Volumetric Atmospheric Corona (No hard bullseye rings)
 * - 3D Orbital Rings around the Core
 * - Single Smooth 3D Bézier Curve per Node
 * - Information Ingestion: Data Photons stream FROM Nodes INTO the Nucleus
 * - Golden Amber Spherical Sparkles + Deep Space Stars
 * - Proportional, Un-stretched Monospace Labels
 * - Responsive 3rd-Pane Centering
 */

class NeuralSpaceScene {
    constructor(canvasContainerId) {
        this.container = document.getElementById(canvasContainerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;

        // Core Objects
        this.nucleusGroup = null;
        this.nucleusCore = null;
        this.orbitalRing1 = null;
        this.orbitalRing2 = null;
        this.starField = null;
        this.sparkleField = null;

        // Strands & Nodes (1 Single 3D Curve per Node)
        this.branchesGroup = null;
        this.sourceNodes = []; // { mesh, sprite, line, data, id, targetPos, curve, initialColor }
        this.pulseParticles = []; // light photons flowing FROM node INTO nucleus
        this.interactiveObjects = []; // Meshes & Sprites for raycasting

        // Raycasting & Interaction
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2(-1000, -1000);
        this.hoveredItem = null;
        this.onNodeClickCallback = null;
        this.onNodeHoverCallback = null;

        // Pane Mode (Centering to 3rd pane vs center of screen)
        this.is3PaneMode = false;

        // Timing & State
        this.clock = new THREE.Clock();
        this.isSynthesizing = false;

        this.init();
    }

    init() {
        const width = window.innerWidth;
        const height = window.innerHeight;

        // 1. Scene & Deep Space Environment
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x020307);
        this.scene.fog = new THREE.FogExp2(0x020307, 0.0028);

        // 2. Camera Setup
        this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 2500);
        this.camera.position.set(0, 8, 55);

        // 3. Renderer with ACES Tone Mapping
        this.renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: true,
            powerPreference: "high-performance"
        });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.25;
        this.container.appendChild(this.renderer.domElement);

        // 4. OrbitControls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.enableZoom = true;
        this.controls.minDistance = 14;
        this.controls.maxDistance = 220;
        this.controls.enablePan = true;
        this.controls.maxPolarAngle = Math.PI * 0.88;
        this.controls.target.set(0, 0, 0);

        // 5. Lighting: Genuine 3D PBR Illumination
        const ambient = new THREE.AmbientLight(0x0e1726, 1.2);
        this.scene.add(ambient);

        // Burning Core Point Light (illuminates nodes and lines from within)
        const nucleusLight = new THREE.PointLight(0xff6611, 4.5, 140, 1.2);
        nucleusLight.position.set(0, 0, 0);
        this.scene.add(nucleusLight);

        // Directional Key Light for specular depth on 3D spheres
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(25, 35, 45);
        this.scene.add(dirLight);

        // 6. Build Scene Foundations
        this.buildStarFieldAndSparkles();
        this.buildNucleus();

        this.branchesGroup = new THREE.Group();
        this.scene.add(this.branchesGroup);

        // 7. Event Listeners
        window.addEventListener('resize', () => this.onWindowResize());
        window.addEventListener('mousemove', (e) => this.onMouseMove(e));
        window.addEventListener('click', (e) => this.onClick(e));

        // Start Animation Loop
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    /* ═══════════════════════════════════════════════
       PANE-AWARE CAMERA VIEW OFFSET
       Centers (0,0,0) or target to the 3rd pane (#right-area)
       ═══════════════════════════════════════════════ */
    setPaneMode(is3Pane) {
        this.is3PaneMode = is3Pane;
        this.updateCameraViewOffset();
    }

    updateCameraViewOffset() {
        const W = window.innerWidth;
        const H = window.innerHeight;

        if (!this.is3PaneMode) {
            this.camera.clearViewOffset();
            this.camera.aspect = W / H;
            this.camera.updateProjectionMatrix();
            return;
        }

        const rightArea = document.getElementById("right-area");
        if (!rightArea) {
            this.camera.clearViewOffset();
            return;
        }

        const rect = rightArea.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            this.camera.clearViewOffset();
            return;
        }

        // Center point of the 3rd pane on screen
        const paneCenterX = rect.left + (rect.width / 2);
        const paneCenterY = rect.top + (rect.height / 2);

        // Shift relative to window center
        const shiftX = paneCenterX - (W / 2);
        const shiftY = paneCenterY - (H / 2);

        this.camera.setViewOffset(W, H, -shiftX, -shiftY, W, H);
        this.camera.aspect = W / H;
        this.camera.updateProjectionMatrix();
    }

    /* ═══════════════════════════════════════════════
       PROCEDURAL CIRCULAR PARTICLE TEXTURE
       Renders soft spherical points instead of squares
       ═══════════════════════════════════════════════ */
    createCircleTexture() {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        const center = size / 2;
        const radius = size / 2;

        const grad = ctx.createRadialGradient(center, center, 0, center, center, radius);
        grad.addColorStop(0.0, 'rgba(255, 255, 255, 1.0)');
        grad.addColorStop(0.35, 'rgba(255, 255, 255, 0.85)');
        grad.addColorStop(0.75, 'rgba(255, 255, 255, 0.2)');
        grad.addColorStop(1.0, 'rgba(255, 255, 255, 0.0)');

        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);

        return new THREE.CanvasTexture(canvas);
    }

    /* ═══════════════════════════════════════════════
       PROCEDURAL GLOW TEXTURE GENERATOR
       ═══════════════════════════════════════════════ */
    createGlowTexture() {
        const size = 256;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0.0, 'rgba(255, 250, 240, 1.0)');
        grad.addColorStop(0.18, 'rgba(255, 110, 15, 0.85)');
        grad.addColorStop(0.45, 'rgba(220, 50, 5, 0.35)');
        grad.addColorStop(0.75, 'rgba(160, 20, 0, 0.1)');
        grad.addColorStop(1.0, 'rgba(0, 0, 0, 0.0)');

        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, size, size);

        return new THREE.CanvasTexture(canvas);
    }

    /* ═══════════════════════════════════════════════
       CENTRAL VOLUMETRIC NUCLEUS
       No hard concentric rings: Smooth Shader Corona + 3D Orbital Rings
       ═══════════════════════════════════════════════ */
    buildNucleus() {
        this.nucleusGroup = new THREE.Group();

        // 1. White-hot Core Sphere
        const coreGeo = new THREE.SphereGeometry(2.5, 32, 32);
        const coreMat = new THREE.MeshStandardMaterial({
            color: 0xff4400,
            emissive: 0xff6600,
            emissiveIntensity: 1.5,
            roughness: 0.1,
            metalness: 0.1
        });
        this.nucleusCore = new THREE.Mesh(coreGeo, coreMat);
        this.nucleusGroup.add(this.nucleusCore);

        // Raycasting target
        this.nucleusCore.userData = { isNucleus: true };
        this.interactiveObjects.push(this.nucleusCore);

        // 2. Smooth Volumetric Corona Shader (Smooth continuous falloff, zero hard bullseye rings)
        const coronaGeo = new THREE.SphereGeometry(4.8, 32, 32);
        const coronaMat = new THREE.ShaderMaterial({
            uniforms: {
                glowColor: { value: new THREE.Color(0xff4400) }
            },
            vertexShader: `
                varying vec3 vNormal;
                void main() {
                    vNormal = normalize(normalMatrix * normal);
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                varying vec3 vNormal;
                uniform vec3 glowColor;
                void main() {
                    // Soft atmospheric falloff from center to edge
                    float intensity = pow(dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.2);
                    gl_FragColor = vec4(glowColor, intensity * 0.65);
                }
            `,
            blending: THREE.AdditiveBlending,
            transparent: true,
            depthWrite: false,
            side: THREE.BackSide
        });
        const coronaMesh = new THREE.Mesh(coronaGeo, coronaMat);
        this.nucleusGroup.add(coronaMesh);

        // 3. Volumetric Glow Billboard (Soft outer flare)
        const glowTex = this.createGlowTexture();
        const spriteMat = new THREE.SpriteMaterial({
            map: glowTex,
            color: 0xff5511,
            transparent: true,
            opacity: 0.85,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        });
        this.nucleusGlowSprite = new THREE.Sprite(spriteMat);
        this.nucleusGlowSprite.scale.set(22, 22, 1);
        this.nucleusGroup.add(this.nucleusGlowSprite);

        // 4. Genuine 3D Orbital Rings (Creates authentic 3D celestial depth)
        const ringMat1 = new THREE.MeshBasicMaterial({
            color: 0xff6600,
            transparent: true,
            opacity: 0.45,
            blending: THREE.AdditiveBlending
        });
        const ringGeo1 = new THREE.TorusGeometry(3.6, 0.035, 16, 80);
        this.orbitalRing1 = new THREE.Mesh(ringGeo1, ringMat1);
        this.orbitalRing1.rotation.x = Math.PI * 0.35;
        this.orbitalRing1.rotation.y = Math.PI * 0.15;
        this.nucleusGroup.add(this.orbitalRing1);

        const ringMat2 = new THREE.MeshBasicMaterial({
            color: 0xffaa22,
            transparent: true,
            opacity: 0.35,
            blending: THREE.AdditiveBlending
        });
        const ringGeo2 = new THREE.TorusGeometry(4.4, 0.03, 16, 80);
        this.orbitalRing2 = new THREE.Mesh(ringGeo2, ringMat2);
        this.orbitalRing2.rotation.x = -Math.PI * 0.25;
        this.orbitalRing2.rotation.z = Math.PI * 0.4;
        this.nucleusGroup.add(this.orbitalRing2);

        this.scene.add(this.nucleusGroup);
    }

    /* ═══════════════════════════════════════════════
       DEEP-SPACE STARS & GOLDEN AMBER SPARKLES
       Both use circular textures (tiny spherical beads, zero squares)
       ═══════════════════════════════════════════════ */
    buildStarFieldAndSparkles() {
        const circleTex = this.createCircleTexture();

        // 1. Distant Starfield (Crisp silver and icy blue spheres)
        const starCount = 2200;
        const starGeo = new THREE.BufferGeometry();
        const starPos = new Float32Array(starCount * 3);
        const starCol = new Float32Array(starCount * 3);

        const colWhite = new THREE.Color(0xf1f5f9);
        const colCyan = new THREE.Color(0x38bdf8);
        const colMuted = new THREE.Color(0x64748b);

        for (let i = 0; i < starCount; i++) {
            const r = 50 + Math.random() * 380;
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos((Math.random() * 2) - 1);

            starPos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
            starPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
            starPos[i * 3 + 2] = r * Math.cos(phi);

            const pick = Math.random();
            const c = pick < 0.65 ? colMuted : (pick < 0.90 ? colWhite : colCyan);
            starCol[i * 3]     = c.r;
            starCol[i * 3 + 1] = c.g;
            starCol[i * 3 + 2] = c.b;
        }

        starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
        starGeo.setAttribute('color', new THREE.BufferAttribute(starCol, 3));

        const starMat = new THREE.PointsMaterial({
            size: 0.32,
            map: circleTex,
            vertexColors: true,
            transparent: true,
            opacity: 0.8,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        });
        this.starField = new THREE.Points(starGeo, starMat);
        this.scene.add(this.starField);

        // 2. Warm Golden/Amber Sparkles (Controlled density: 85 tiny luminous spheres)
        const sparkleCount = 85;
        const sparkleGeo = new THREE.BufferGeometry();
        const sparklePos = new Float32Array(sparkleCount * 3);
        const sparkleCol = new Float32Array(sparkleCount * 3);

        for (let i = 0; i < sparkleCount; i++) {
            const r = 5.5 + Math.random() * 24;
            const theta = Math.random() * Math.PI * 2;
            const y = (Math.random() - 0.5) * 16;

            sparklePos[i * 3]     = r * Math.cos(theta);
            sparklePos[i * 3 + 1] = y;
            sparklePos[i * 3 + 2] = r * Math.sin(theta);

            // Rich warm golden amber
            sparkleCol[i * 3]     = 1.0;
            sparkleCol[i * 3 + 1] = 0.68 + Math.random() * 0.22;
            sparkleCol[i * 3 + 2] = 0.12;
        }

        sparkleGeo.setAttribute('position', new THREE.BufferAttribute(sparklePos, 3));
        sparkleGeo.setAttribute('color', new THREE.BufferAttribute(sparkleCol, 3));

        const sparkleMat = new THREE.PointsMaterial({
            size: 0.35,
            map: circleTex,
            vertexColors: true,
            transparent: true,
            opacity: 0.65,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        });
        this.sparkleField = new THREE.Points(sparkleGeo, sparkleMat);
        this.scene.add(this.sparkleField);
    }

    /* ═══════════════════════════════════════════════
       CLEAN, COMPACT MONOSPACE 3D TEXT LABEL
       Rendered ON TOP of nodes with depthTest: false & renderOrder: 9999
       ═══════════════════════════════════════════════ */
    createTextSprite(source, trustHex) {
        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 180;
        const ctx = canvas.getContext('2d');

        let domain = source.url_or_filename || "SOURCE";
        try {
            if (source.source_type === "web") {
                domain = new URL(source.url_or_filename).hostname.toUpperCase().replace(/^WWW\./, '');
            } else {
                domain = domain.toUpperCase();
            }
        } catch (_) {
            domain = domain.toUpperCase();
        }

        const title = (source.title || "GROUND TRUTH REFERENCE").toUpperCase();
        const trustPercent = ((source.baseline_trust_score ?? 0.5) * 100).toFixed(0);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Sleek dark frosted pill container with border
        ctx.fillStyle = 'rgba(4, 7, 18, 0.82)';
        if (ctx.roundRect) {
            ctx.roundRect(4, 4, canvas.width - 8, canvas.height - 8, 14);
        } else {
            ctx.fillRect(4, 4, canvas.width - 8, canvas.height - 8);
        }
        ctx.fill();

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Line 1: Domain Name (Large & Crisp)
        ctx.font = '700 30px "JetBrains Mono", "Courier New", monospace';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(domain, 20, 48);

        // Line 2: Trust badge inline (Colored by trust factor)
        ctx.font = '700 24px "JetBrains Mono", monospace';
        ctx.fillStyle = `#${trustHex.toString(16).padStart(6, '0')}`;
        ctx.fillText(`[${source.source_id}] TRUST ${trustPercent}%`, 20, 96);

        // Line 3: Title snippet
        ctx.font = '500 20px "JetBrains Mono", monospace';
        ctx.fillStyle = '#cbd5e1';
        const displayTitle = title.length > 34 ? title.substring(0, 32) + '...' : title;
        ctx.fillText(displayTitle, 20, 142);

        const texture = new THREE.CanvasTexture(canvas);
        texture.minFilter = THREE.LinearFilter;
        texture.magFilter = THREE.LinearFilter;

        const spriteMat = new THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            opacity: 0.95,
            depthTest: false,  // ALWAYS RENDERED ON TOP OVER NODES
            depthWrite: false
        });

        const sprite = new THREE.Sprite(spriteMat);
        sprite.renderOrder = 9999; // Highest render order: rendered directly on top of 3D objects
        sprite.scale.set(5.2, 1.82, 1.0); // Prominent and readable
        return sprite;
    }

    /* ═══════════════════════════════════════════════
       POPULATE SOURCES:
       - DEFINED 3D GLOWING TUBULAR PATHS (Not thin 1px lines)
       - SMALLER CRISP PBR SPHERES (Radius 0.42)
       - TEXT LABELS RENDERED ON TOP DIRECTLY ABOVE NODES
       - DATA PHOTONS FLOW FROM NODE INTO NUCLEUS
       ═══════════════════════════════════════════════ */
    populateSources(sources, onComplete) {
        // Clear previous lines, nodes, pulses
        while (this.branchesGroup.children.length > 0) {
            const obj = this.branchesGroup.children[0];
            this.branchesGroup.remove(obj);
        }
        this.sourceNodes = [];
        this.pulseParticles = [];
        this.interactiveObjects = [this.nucleusCore];

        if (!sources || sources.length === 0) {
            if (onComplete) onComplete();
            return;
        }

        this.updateCameraViewOffset();

        const count = sources.length;
        const baseRadius = 24;

        sources.forEach((source, index) => {
            // Distribute nodes in authentic 3D radial space
            const angleStep = (Math.PI * 2.0) / Math.max(count, 1);
            const angle = (index * angleStep) + 0.25;
            const elevation = ((index % 3) - 1) * 7 + (Math.sin(index * 2) * 4);
            const dist = baseRadius + (Math.cos(index * 1.8) * 5) + 4;

            // Target node 3D coordinate
            const tx = Math.cos(angle) * dist;
            const ty = elevation;
            const tz = Math.sin(angle) * dist;
            const targetPos = new THREE.Vector3(tx, ty, tz);

            // Trust Factor Color Mapping
            const trust = source.baseline_trust_score ?? 0.5;
            let hexColor;
            if (trust >= 0.70) {
                hexColor = 0x10b981; // High Trust -> Vivid Emerald Green
            } else if (trust >= 0.45) {
                hexColor = 0xf59e0b; // Mid Trust -> Warm Amber Yellow
            } else {
                hexColor = 0xef4444; // Low Trust -> Warning Coral Red
            }

            // ─── 1. DEFINED 3D GLOWING TUBE PATH (3D Cylindrical Geometry) ───
            const startPos = new THREE.Vector3(0, 0, 0);
            const midProg = 0.5;
            const controlPos = new THREE.Vector3(
                (tx * midProg) + (Math.sin(index * 1.6) * 4),
                (ty * midProg) + 4.5,
                (tz * midProg) + (Math.cos(index * 1.6) * 4)
            );

            const curve = new THREE.QuadraticBezierCurve3(startPos, controlPos, targetPos);

            // 3D Tube Geometry gives real physical width, volume, and illumination!
            const tubeGeo = new THREE.TubeGeometry(curve, 54, 0.08, 8, false);
            const tubeMat = new THREE.MeshStandardMaterial({
                color: hexColor,
                emissive: hexColor,
                emissiveIntensity: 0.9,
                roughness: 0.3,
                metalness: 0.7
            });
            const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
            this.branchesGroup.add(tubeMesh);

            // Inner laser core line for intense luminance
            const coreLineGeo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48));
            const coreLineMat = new THREE.LineBasicMaterial({
                color: 0xffffff,
                transparent: true,
                opacity: 0.75,
                blending: THREE.AdditiveBlending
            });
            const coreLine = new THREE.Line(coreLineGeo, coreLineMat);
            this.branchesGroup.add(coreLine);

            // ─── 2. SMALLER CRISP 3D PBR SPHERE NODE (Radius 0.42) ───
            const nodeGeo = new THREE.SphereGeometry(0.42, 24, 24);
            const nodeMat = new THREE.MeshStandardMaterial({
                color: hexColor,
                emissive: hexColor,
                emissiveIntensity: 1.2,
                roughness: 0.2,
                metalness: 0.8
            });
            const nodeMesh = new THREE.Mesh(nodeGeo, nodeMat);
            nodeMesh.position.copy(targetPos);
            nodeMesh.userData = {
                sourceId: source.source_id,
                source: source,
                tube: tubeMesh,
                initialColor: hexColor
            };
            this.branchesGroup.add(nodeMesh);

            // ─── 3. PROPORTIONAL 3D LABEL RENDERED DIRECTLY OVER NODE ───
            const textSprite = this.createTextSprite(source, hexColor);
            // Positioned right above the node so it rests over it
            textSprite.position.set(tx, ty + 1.45, tz);
            textSprite.userData = {
                sourceId: source.source_id,
                source: source,
                parentMesh: nodeMesh,
                tube: tubeMesh
            };
            this.branchesGroup.add(textSprite);

            // Register interactives
            this.interactiveObjects.push(nodeMesh);
            this.interactiveObjects.push(textSprite);

            this.sourceNodes.push({
                mesh: nodeMesh,
                sprite: textSprite,
                tube: tubeMesh,
                data: source,
                id: source.source_id,
                targetPos: targetPos,
                curve: curve,
                initialColor: hexColor
            });

            // ─── 4. DATA PHOTON: FLOWS FROM NODE INTO THE NUCLEUS ───
            const pulseGeo = new THREE.SphereGeometry(0.18, 16, 16);
            const pulseMat = new THREE.MeshStandardMaterial({
                color: 0xffffff,
                emissive: hexColor,
                emissiveIntensity: 1.8,
                roughness: 0.1
            });
            const pulse = new THREE.Mesh(pulseGeo, pulseMat);
            this.branchesGroup.add(pulse);

            this.pulseParticles.push({
                mesh: pulse,
                curve: curve,
                progress: Math.random(),
                speed: 0.0035 + Math.random() * 0.003
            });

            // ─── STAGGERED SPAWN: TUBE GROWS OUTWARD -> NODE POPS IN -> LABEL APPEARS ───
            const staggerDelay = index * 0.08;

            tubeMesh.scale.set(0.001, 0.001, 0.001);
            coreLine.scale.set(0.001, 0.001, 0.001);
            nodeMesh.scale.set(0.001, 0.001, 0.001);
            textSprite.scale.set(0.001, 0.001, 0.001);
            textSprite.material.opacity = 0;
            pulse.visible = false;

            if (typeof gsap !== 'undefined') {
                // 1. Branch grows outward from nucleus
                gsap.to(tubeMesh.scale, {
                    x: 1.0, y: 1.0, z: 1.0,
                    duration: 0.75,
                    delay: staggerDelay,
                    ease: "power2.out"
                });
                gsap.to(coreLine.scale, {
                    x: 1.0, y: 1.0, z: 1.0,
                    duration: 0.75,
                    delay: staggerDelay,
                    ease: "power2.out"
                });

                // 2. Node pops in at the tip as the branch arrives
                gsap.to(nodeMesh.scale, {
                    x: 1.0, y: 1.0, z: 1.0,
                    duration: 0.45,
                    delay: staggerDelay + 0.6,
                    ease: "back.out(2.2)",
                    onComplete: () => { pulse.visible = true; }
                });

                // 3. Text label scales in directly over the node
                gsap.to(textSprite.scale, {
                    x: 5.2, y: 1.82, z: 1.0,
                    duration: 0.4,
                    delay: staggerDelay + 0.75,
                    ease: "power2.out"
                });
                gsap.to(textSprite.material, {
                    opacity: 0.95,
                    duration: 0.4,
                    delay: staggerDelay + 0.75
                });
            } else {
                tubeMesh.scale.set(1.0, 1.0, 1.0);
                coreLine.scale.set(1.0, 1.0, 1.0);
                nodeMesh.scale.set(1.0, 1.0, 1.0);
                textSprite.scale.set(5.2, 1.82, 1.0);
                textSprite.material.opacity = 0.95;
                pulse.visible = true;
            }
        });

        // Compute total animation completion timestamp
        const totalDuration = Math.min(0.75 + (count * 0.08) + 0.8, 2.2);
        if (onComplete) {
            setTimeout(onComplete, totalDuration * 1000);
        }

        // Center overview onto the 3rd pane
        this.focusOverview();
    }

    /* ═══════════════════════════════════════════════
       CAMERA NAVIGATION & CENTERING
       ═══════════════════════════════════════════════ */
    focusOverview() {
        this.updateCameraViewOffset();

        if (typeof gsap !== 'undefined') {
            gsap.to(this.controls.target, {
                x: 0,
                y: 0,
                z: 0,
                duration: 1.6,
                ease: "power2.out"
            });
            gsap.to(this.camera.position, {
                x: 0,
                y: 8,
                z: 55,
                duration: 1.8,
                ease: "power2.out"
            });
        } else {
            this.controls.target.set(0, 0, 0);
            this.camera.position.set(0, 8, 55);
        }
    }

    focusNodeById(sourceId) {
        const found = this.sourceNodes.find(n => n.id === sourceId);
        if (!found) return;

        this.updateCameraViewOffset();

        // Visual highlights
        this.sourceNodes.forEach(n => {
            const isTarget = n.id === sourceId;
            n.mesh.scale.setScalar(isTarget ? 1.7 : 0.85);
            n.sprite.material.opacity = isTarget ? 1.0 : 0.35;
            if (n.tube) {
                n.tube.material.emissiveIntensity = isTarget ? 1.8 : 0.5;
            }
        });

        const target = found.targetPos;
        if (typeof gsap !== 'undefined') {
            gsap.to(this.controls.target, {
                x: target.x,
                y: target.y,
                z: target.z,
                duration: 1.4,
                ease: "power2.out"
            });
            gsap.to(this.camera.position, {
                x: target.x,
                y: target.y + 3.5,
                z: target.z + 20,
                duration: 1.6,
                ease: "power2.out"
            });
        } else {
            this.controls.target.copy(target);
            this.camera.position.set(target.x, target.y + 3.5, target.z + 20);
        }
    }

    resetHighlights() {
        this.sourceNodes.forEach(n => {
            n.mesh.scale.set(1.0, 1.0, 1.0);
            n.sprite.material.opacity = 0.95;
            if (n.tube) {
                n.tube.material.emissiveIntensity = 0.9;
            }
        });
    }

    setSynthesizing(active) {
        this.isSynthesizing = active;
    }

    /* ═══════════════════════════════════════════════
       INTERACTION: HOVER & CLICK RAYCASTING
       ═══════════════════════════════════════════════ */
    onMouseMove(event) {
        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

        if (this.interactiveObjects.length > 0) {
            this.raycaster.setFromCamera(this.mouse, this.camera);
            const intersects = this.raycaster.intersectObjects(this.interactiveObjects);

            if (intersects.length > 0) {
                const hit = intersects[0].object;
                if (this.hoveredItem !== hit) {
                    this.hoveredItem = hit;
                    document.body.style.cursor = 'pointer';

                    const src = hit.userData.source;
                    if (this.onNodeHoverCallback) {
                        this.onNodeHoverCallback(src, event.clientX, event.clientY);
                    }
                }
            } else {
                if (this.hoveredItem) {
                    this.hoveredItem = null;
                    document.body.style.cursor = 'default';
                    if (this.onNodeHoverCallback) {
                        this.onNodeHoverCallback(null);
                    }
                }
            }
        }
    }

    onClick(event) {
        if (!this.interactiveObjects.length) return;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObjects(this.interactiveObjects);

        if (intersects.length > 0) {
            const hit = intersects[0].object;
            if (hit.userData.isNucleus) {
                this.resetHighlights();
                this.focusOverview();
                return;
            }
            const src = hit.userData.source;
            if (this.onNodeClickCallback && src) {
                this.onNodeClickCallback(src);
            }
        }
    }

    onWindowResize() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        this.camera.aspect = width / height;
        this.updateCameraViewOffset();
        this.renderer.setSize(width, height);
    }

    /* ═══════════════════════════════════════════════
       MAIN RENDER & DYNAMICS LOOP
       ═══════════════════════════════════════════════ */
    animate() {
        requestAnimationFrame(this.animate);
        const elapsedTime = this.clock.getElapsedTime();

        // 1. Starfield slow drift
        if (this.starField) {
            this.starField.rotation.y = elapsedTime * 0.005;
        }

        // 2. Swirling golden amber sparkles
        if (this.sparkleField) {
            this.sparkleField.rotation.y = elapsedTime * 0.04;
            this.sparkleField.rotation.x = Math.sin(elapsedTime * 0.15) * 0.03;
        }

        // 3. Nucleus Dynamics & 3D Orbital Rings
        if (this.nucleusGroup) {
            const pulseRate = this.isSynthesizing ? 5.5 : 1.6;
            const pulse = Math.sin(elapsedTime * pulseRate) * 0.08 + 1.0;

            this.nucleusCore.scale.setScalar(pulse);

            if (this.nucleusGlowSprite) {
                const s = (22 + Math.sin(elapsedTime * 2.0) * 2.5) * (this.isSynthesizing ? 1.25 : 1.0);
                this.nucleusGlowSprite.scale.set(s, s, 1);
            }

            // Slowly orbit the 3D celestial gimbal rings
            if (this.orbitalRing1) {
                this.orbitalRing1.rotation.z = elapsedTime * 0.35;
            }
            if (this.orbitalRing2) {
                this.orbitalRing2.rotation.y = elapsedTime * 0.25;
            }

            this.nucleusGroup.rotation.y = elapsedTime * (this.isSynthesizing ? 0.4 : 0.06);
        }

        // 4. Information Ingestion: Data Photons Flow FROM NODES INTO THE NUCLEUS
        this.pulseParticles.forEach(p => {
            // Count DOWN towards 0 (0 = nucleus, 1 = node)
            p.progress -= p.speed * (this.isSynthesizing ? 2.5 : 1.0);
            if (p.progress < 0.0) {
                p.progress = 1.0; // resets at the node
            }
            const pt = p.curve.getPoint(p.progress);
            p.mesh.position.copy(pt);
        });

        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}

window.NeuralSpaceScene = NeuralSpaceScene;
