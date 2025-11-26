/**
 * 3D社交关系网络图谱 - 基于Three.js
 * 支持多种视觉风格主题
 */

class SocialGraph3D {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Container ${containerId} not found`);
            return;
        }

        // 场景、相机、渲染器
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;

        // 数据
        this.nodes = [];
        this.edges = [];
        this.nodeObjects = new Map(); // Three.js节点对象
        this.edgeObjects = [];

        // 当前主题
        this.currentTheme = 'default';

        // 主题配置
        this.themes = {
            default: {
                name: '默认',
                backgroundColor: 0x0a0a0a,
                fogColor: 0x0a0a0a,
                fogNear: 50,
                fogFar: 200,
                nodeColor: 0x4fc3f7,
                nodeEmissive: 0x1976d2,
                edgeColor: 0x42a5f5,
                edgeOpacity: 0.3,
                ambientLight: 0x404040,
                directionalLight: 0xffffff,
                gridColor: 0x333333,
                particleColor: 0x4fc3f7
            },
            cyberpunk: {
                name: '赛博朋克',
                backgroundColor: 0x0d001a,
                fogColor: 0x0d001a,
                fogNear: 40,
                fogFar: 180,
                nodeColor: 0xff00ff,
                nodeEmissive: 0xff00aa,
                edgeColor: 0x00ffff,
                edgeOpacity: 0.5,
                ambientLight: 0x330033,
                directionalLight: 0xff00ff,
                gridColor: 0xff00ff,
                particleColor: 0x00ffff
            },
            scifi: {
                name: '科幻',
                backgroundColor: 0x000510,
                fogColor: 0x000510,
                fogNear: 60,
                fogFar: 220,
                nodeColor: 0x00ffaa,
                nodeEmissive: 0x00aa77,
                edgeColor: 0x0088ff,
                edgeOpacity: 0.4,
                ambientLight: 0x001133,
                directionalLight: 0x00aaff,
                gridColor: 0x003366,
                particleColor: 0x00ffaa
            },
            matrix: {
                name: '黑客帝国',
                backgroundColor: 0x000000,
                fogColor: 0x000000,
                fogNear: 50,
                fogFar: 200,
                nodeColor: 0x00ff00,
                nodeEmissive: 0x00aa00,
                edgeColor: 0x00ff00,
                edgeOpacity: 0.3,
                ambientLight: 0x001100,
                directionalLight: 0x00ff00,
                gridColor: 0x003300,
                particleColor: 0x00ff00
            },
            sunset: {
                name: '日落',
                backgroundColor: 0x1a0a0a,
                fogColor: 0x1a0a0a,
                fogNear: 50,
                fogFar: 200,
                nodeColor: 0xff6b35,
                nodeEmissive: 0xff4500,
                edgeColor: 0xffa500,
                edgeOpacity: 0.4,
                ambientLight: 0x331100,
                directionalLight: 0xff6b35,
                gridColor: 0x442200,
                particleColor: 0xff6b35
            },
            ocean: {
                name: '海洋',
                backgroundColor: 0x000a1a,
                fogColor: 0x000a1a,
                fogNear: 50,
                fogFar: 200,
                nodeColor: 0x00bfff,
                nodeEmissive: 0x0088cc,
                edgeColor: 0x1e90ff,
                edgeOpacity: 0.4,
                ambientLight: 0x001133,
                directionalLight: 0x00bfff,
                gridColor: 0x003366,
                particleColor: 0x00bfff
            }
        };

        // 动画相关
        this.animationId = null;
        this.clock = new THREE.Clock();

        // 粒子系统
        this.particles = null;

        // 选中的节点
        this.selectedNode = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        this.init();
    }

    init() {
        console.log('🎨 SocialGraph3D.init() 开始...');

        // 检查THREE是否存在
        if (typeof THREE === 'undefined') {
            console.error('❌ THREE.js 未加载');
            return;
        }
        console.log('✅ THREE.js 已加载');

        // 检查OrbitControls是否存在
        if (typeof THREE.OrbitControls === 'undefined') {
            console.error('❌ THREE.OrbitControls 未加载');
            console.log('可用的THREE属性:', Object.keys(THREE));
            return;
        }
        console.log('✅ THREE.OrbitControls 已加载');

        // 创建场景
        this.scene = new THREE.Scene();
        const theme = this.themes[this.currentTheme];
        this.scene.background = new THREE.Color(theme.backgroundColor);
        this.scene.fog = new THREE.Fog(theme.fogColor, theme.fogNear, theme.fogFar);

        // 创建相机
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        console.log('📐 容器尺寸:', { width, height });

        this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
        this.camera.position.set(0, 20, 40);  // 调整相机位置更近一些

        // 创建渲染器
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);
        console.log('✅ 渲染器已创建并添加到容器');

        // 添加轨道控制器
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 10;  // 减小最小距离
        this.controls.maxDistance = 200;  // 减小最大距离
        console.log('✅ 轨道控制器已创建');

        // 添加光源
        this.setupLights();

        // 添加网格辅助线
        this.setupGrid();

        // 添加粒子背景
        this.setupParticles();

        // 添加事件监听
        window.addEventListener('resize', () => this.onWindowResize());
        this.renderer.domElement.addEventListener('click', (e) => this.onMouseClick(e));
        this.renderer.domElement.addEventListener('mousemove', (e) => this.onMouseMove(e));

        // 启动动画循环
        this.animate();

        console.log('✅ SocialGraph3D 初始化完成');
    }

    setupLights() {
        const theme = this.themes[this.currentTheme];

        // 环境光
        const ambientLight = new THREE.AmbientLight(theme.ambientLight, 0.5);
        this.scene.add(ambientLight);

        // 方向光
        const directionalLight = new THREE.DirectionalLight(theme.directionalLight, 0.8);
        directionalLight.position.set(50, 100, 50);
        this.scene.add(directionalLight);

        // 点光源（跟随相机）
        const pointLight = new THREE.PointLight(theme.nodeColor, 0.5, 200);
        this.camera.add(pointLight);
        this.scene.add(this.camera);
    }

    setupGrid() {
        const theme = this.themes[this.currentTheme];

        // 移除旧网格
        const oldGrid = this.scene.getObjectByName('grid');
        if (oldGrid) this.scene.remove(oldGrid);

        // 创建网格
        const gridHelper = new THREE.GridHelper(200, 20, theme.gridColor, theme.gridColor);
        gridHelper.name = 'grid';
        gridHelper.material.opacity = 0.2;
        gridHelper.material.transparent = true;
        this.scene.add(gridHelper);
    }

    setupParticles() {
        const theme = this.themes[this.currentTheme];

        // 移除旧粒子
        if (this.particles) {
            this.scene.remove(this.particles);
            this.particles.geometry.dispose();
            this.particles.material.dispose();
        }

        // 创建粒子几何体
        const particleCount = 1000;
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);

        const color = new THREE.Color(theme.particleColor);

        for (let i = 0; i < particleCount; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 300;
            positions[i * 3 + 1] = (Math.random() - 0.5) * 300;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 300;

            colors[i * 3] = color.r;
            colors[i * 3 + 1] = color.g;
            colors[i * 3 + 2] = color.b;
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.5,
            vertexColors: true,
            transparent: true,
            opacity: 0.6,
            blending: THREE.AdditiveBlending
        });

        this.particles = new THREE.Points(geometry, material);
        this.scene.add(this.particles);
    }

    setTheme(themeName) {
        if (!this.themes[themeName]) {
            console.warn(`Theme ${themeName} not found`);
            return;
        }

        console.log(`🎨 切换主题: ${this.currentTheme} -> ${themeName}`);
        console.log(`📊 当前数据状态: ${this.nodeObjects.size} 个节点, ${this.edgeObjects.length} 条边`);

        this.currentTheme = themeName;
        const theme = this.themes[themeName];

        // 更新场景背景和雾
        this.scene.background = new THREE.Color(theme.backgroundColor);
        this.scene.fog.color = new THREE.Color(theme.fogColor);
        this.scene.fog.near = theme.fogNear;
        this.scene.fog.far = theme.fogFar;

        // 更新光源
        this.scene.children.forEach(child => {
            if (child instanceof THREE.AmbientLight) {
                child.color = new THREE.Color(theme.ambientLight);
            } else if (child instanceof THREE.DirectionalLight) {
                child.color = new THREE.Color(theme.directionalLight);
            } else if (child instanceof THREE.PointLight) {
                child.color = new THREE.Color(theme.nodeColor);
            }
        });

        // 更新网格
        this.setupGrid();

        // 更新粒子
        this.setupParticles();

        // 更新节点和边
        if (this.nodeObjects.size > 0) {
            this.updateNodesTheme();
            console.log('✅ 已更新节点主题');
        } else {
            console.warn('⚠️ 没有节点数据，跳过节点主题更新');
        }

        if (this.edgeObjects.length > 0) {
            this.updateEdgesTheme();
            console.log('✅ 已更新边主题');
        } else {
            console.warn('⚠️ 没有边数据，跳过边主题更新');
        }

        console.log('✅ 主题切换完成');
    }

    updateNodesTheme() {
        const theme = this.themes[this.currentTheme];

        this.nodeObjects.forEach(nodeObj => {
            nodeObj.children.forEach(child => {
                if (child instanceof THREE.Mesh) {
                    // 更新球体颜色
                    if (child.geometry instanceof THREE.SphereGeometry) {
                        child.material.color = new THREE.Color(theme.nodeColor);
                        child.material.emissive = new THREE.Color(theme.nodeEmissive);
                    }
                    // 更新光环颜色
                    else if (child.geometry instanceof THREE.RingGeometry) {
                        child.material.color = new THREE.Color(theme.nodeColor);
                    }
                }
            });
        });
    }

    updateEdgesTheme() {
        const theme = this.themes[this.currentTheme];

        this.edgeObjects.forEach(edge => {
            edge.material.color = new THREE.Color(theme.edgeColor);
            edge.material.opacity = theme.edgeOpacity;
        });
    }

    loadData(nodes, edges) {
        console.log(`📥 loadData 被调用: ${nodes.length} 个节点, ${edges.length} 条边`);
        console.log('📊 节点示例:', nodes[0]);
        console.log('📊 边示例:', edges[0]);

        this.nodes = nodes;
        this.edges = edges;

        // 清除旧数据
        this.clearGraph();

        // 创建节点
        this.createNodes();
        console.log(`✅ 已创建 ${this.nodeObjects.size} 个节点对象`);

        // 创建边
        this.createEdges();
        console.log(`✅ 已创建 ${this.edgeObjects.length} 个边对象`);

        // 应用力导向布局
        this.applyForceLayout();
        console.log('✅ 力导向布局已应用');

        console.log('✅ loadData 完成');
    }

    clearGraph() {
        // 清除节点
        this.nodeObjects.forEach(nodeObj => {
            this.scene.remove(nodeObj);
            nodeObj.traverse(child => {
                if (child.geometry) child.geometry.dispose();
                if (child.material) child.material.dispose();
            });
        });
        this.nodeObjects.clear();

        // 清除边
        this.edgeObjects.forEach(edge => {
            this.scene.remove(edge);
            edge.geometry.dispose();
            edge.material.dispose();
        });
        this.edgeObjects = [];
    }

    createNodes() {
        const theme = this.themes[this.currentTheme];

        this.nodes.forEach(node => {
            const group = new THREE.Group();
            group.userData = { ...node, type: 'node' };

            // 计算节点大小（基于强度）- 增大基础大小
            const baseSize = 3;  // 从2增加到3
            const size = baseSize + (node.strength || 0) * 0.05;  // 降低strength的影响

            // 创建球体
            const geometry = new THREE.SphereGeometry(size, 32, 32);
            const material = new THREE.MeshPhongMaterial({
                color: theme.nodeColor,
                emissive: theme.nodeEmissive,
                emissiveIntensity: 0.5,  // 增加发光强度
                shininess: 100,
                transparent: true,
                opacity: 0.95  // 增加不透明度
            });
            const sphere = new THREE.Mesh(geometry, material);
            group.add(sphere);

            // 添加光环效果
            const ringGeometry = new THREE.RingGeometry(size * 1.5, size * 1.8, 32);
            const ringMaterial = new THREE.MeshBasicMaterial({
                color: theme.nodeColor,
                transparent: true,
                opacity: 0.4,  // 增加光环不透明度
                side: THREE.DoubleSide
            });
            const ring = new THREE.Mesh(ringGeometry, ringMaterial);
            ring.rotation.x = Math.PI / 2;
            group.add(ring);

            // 添加文本标签（使用Sprite）
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            canvas.width = 256;
            canvas.height = 64;
            context.fillStyle = 'rgba(255, 255, 255, 0.95)';  // 增加文字不透明度
            context.font = 'Bold 28px Arial';  // 增大字体
            context.textAlign = 'center';
            context.fillText(node.label || node.id, 128, 36);

            const texture = new THREE.CanvasTexture(canvas);
            const spriteMaterial = new THREE.SpriteMaterial({ map: texture, transparent: true });
            const sprite = new THREE.Sprite(spriteMaterial);
            sprite.scale.set(12, 3, 1);  // 增大标签尺寸
            sprite.position.y = size + 3;
            group.add(sprite);

            // 随机初始位置
            group.position.set(
                (Math.random() - 0.5) * 100,
                (Math.random() - 0.5) * 100,
                (Math.random() - 0.5) * 100
            );

            this.scene.add(group);
            this.nodeObjects.set(node.id, group);
        });
    }

    createEdges() {
        const theme = this.themes[this.currentTheme];

        this.edges.forEach(edge => {
            const sourceNode = this.nodeObjects.get(edge.source);
            const targetNode = this.nodeObjects.get(edge.target);

            if (!sourceNode || !targetNode) return;

            const points = [
                sourceNode.position.clone(),
                targetNode.position.clone()
            ];

            const geometry = new THREE.BufferGeometry().setFromPoints(points);
            const material = new THREE.LineBasicMaterial({
                color: theme.edgeColor,
                transparent: true,
                opacity: theme.edgeOpacity,
                linewidth: 1
            });

            const line = new THREE.Line(geometry, material);
            line.userData = { source: edge.source, target: edge.target, strength: edge.strength };
            this.scene.add(line);
            this.edgeObjects.push(line);
        });
    }

    applyForceLayout() {
        // 简化的力导向布局算法
        const iterations = 100;
        const k = 30; // 理想距离
        const c_rep = 5000; // 排斥力系数
        const c_spring = 0.1; // 弹簧力系数

        for (let iter = 0; iter < iterations; iter++) {
            const forces = new Map();

            // 初始化力
            this.nodeObjects.forEach((node, id) => {
                forces.set(id, new THREE.Vector3(0, 0, 0));
            });

            // 计算排斥力
            this.nodeObjects.forEach((node1, id1) => {
                this.nodeObjects.forEach((node2, id2) => {
                    if (id1 === id2) return;

                    const delta = node1.position.clone().sub(node2.position);
                    const distance = delta.length() || 1;
                    const force = delta.normalize().multiplyScalar(c_rep / (distance * distance));

                    forces.get(id1).add(force);
                });
            });

            // 计算弹簧力
            this.edges.forEach(edge => {
                const node1 = this.nodeObjects.get(edge.source);
                const node2 = this.nodeObjects.get(edge.target);

                if (!node1 || !node2) return;

                const delta = node2.position.clone().sub(node1.position);
                const distance = delta.length() || 1;
                const force = delta.normalize().multiplyScalar(c_spring * (distance - k));

                forces.get(edge.source).add(force);
                forces.get(edge.target).sub(force);
            });

            // 应用力（使用阻尼）
            const damping = 1 - (iter / iterations) * 0.5;
            this.nodeObjects.forEach((node, id) => {
                const force = forces.get(id).multiplyScalar(damping);
                node.position.add(force);
            });
        }

        // 更新边的位置
        this.updateEdges();
    }

    updateEdges() {
        this.edgeObjects.forEach(edge => {
            const sourceNode = this.nodeObjects.get(edge.userData.source);
            const targetNode = this.nodeObjects.get(edge.userData.target);

            if (sourceNode && targetNode) {
                const positions = edge.geometry.attributes.position.array;
                positions[0] = sourceNode.position.x;
                positions[1] = sourceNode.position.y;
                positions[2] = sourceNode.position.z;
                positions[3] = targetNode.position.x;
                positions[4] = targetNode.position.y;
                positions[5] = targetNode.position.z;
                edge.geometry.attributes.position.needsUpdate = true;
            }
        });
    }

    onMouseClick(event) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);

        const intersects = [];
        this.nodeObjects.forEach(nodeObj => {
            const sphereMesh = nodeObj.children.find(child => child instanceof THREE.Mesh);
            if (sphereMesh) {
                const result = this.raycaster.intersectObject(sphereMesh);
                if (result.length > 0) {
                    intersects.push({ object: nodeObj, distance: result[0].distance });
                }
            }
        });

        if (intersects.length > 0) {
            // 选中最近的节点
            intersects.sort((a, b) => a.distance - b.distance);
            this.selectNode(intersects[0].object);
        } else {
            this.deselectNode();
        }
    }

    onMouseMove(event) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);

        let hovered = false;
        this.nodeObjects.forEach(nodeObj => {
            const sphereMesh = nodeObj.children.find(child => child instanceof THREE.Mesh);
            if (sphereMesh) {
                const intersects = this.raycaster.intersectObject(sphereMesh);
                if (intersects.length > 0) {
                    hovered = true;
                    sphereMesh.material.emissiveIntensity = 0.6;
                } else {
                    sphereMesh.material.emissiveIntensity = nodeObj === this.selectedNode ? 0.8 : 0.3;
                }
            }
        });

        this.renderer.domElement.style.cursor = hovered ? 'pointer' : 'default';
    }

    selectNode(nodeObj) {
        // 取消之前的选中
        if (this.selectedNode) {
            const prevMesh = this.selectedNode.children.find(child => child instanceof THREE.Mesh);
            if (prevMesh) {
                prevMesh.material.emissiveIntensity = 0.3;
                prevMesh.scale.set(1, 1, 1);
            }
        }

        // 选中新节点
        this.selectedNode = nodeObj;
        const mesh = nodeObj.children.find(child => child instanceof THREE.Mesh);
        if (mesh) {
            mesh.material.emissiveIntensity = 0.8;
            mesh.scale.set(1.3, 1.3, 1.3);
        }

        // 高亮相关边
        this.highlightConnectedEdges(nodeObj.userData.id);

        // 触发自定义事件
        const event = new CustomEvent('nodeSelected', { detail: nodeObj.userData });
        this.container.dispatchEvent(event);
    }

    deselectNode() {
        if (this.selectedNode) {
            const mesh = this.selectedNode.children.find(child => child instanceof THREE.Mesh);
            if (mesh) {
                mesh.material.emissiveIntensity = 0.3;
                mesh.scale.set(1, 1, 1);
            }
            this.selectedNode = null;
        }

        // 重置所有边
        this.resetEdgeHighlight();
    }

    highlightConnectedEdges(nodeId) {
        const theme = this.themes[this.currentTheme];

        this.edgeObjects.forEach(edge => {
            if (edge.userData.source === nodeId || edge.userData.target === nodeId) {
                edge.material.opacity = 0.9;
                edge.material.color = new THREE.Color(theme.nodeColor);
            } else {
                edge.material.opacity = 0.1;
            }
        });
    }

    resetEdgeHighlight() {
        const theme = this.themes[this.currentTheme];

        this.edgeObjects.forEach(edge => {
            edge.material.opacity = theme.edgeOpacity;
            edge.material.color = new THREE.Color(theme.edgeColor);
        });
    }

    onWindowResize() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());

        const delta = this.clock.getDelta();

        // 更新控制器
        this.controls.update();

        // 旋转粒子
        if (this.particles) {
            this.particles.rotation.y += delta * 0.05;
        }

        // 节点轻微浮动动画
        this.nodeObjects.forEach((nodeObj, id) => {
            const time = Date.now() * 0.001;
            const offset = parseInt(id.slice(-4), 16) || 0;
            nodeObj.position.y += Math.sin(time + offset) * 0.01;

            // 光环旋转
            const ring = nodeObj.children.find(child => child.geometry instanceof THREE.RingGeometry);
            if (ring) {
                ring.rotation.z += delta * 0.5;
            }
        });

        // 边缘发光效果
        this.edgeObjects.forEach(edge => {
            const time = Date.now() * 0.001;
            edge.material.opacity = this.themes[this.currentTheme].edgeOpacity + Math.sin(time) * 0.05;
        });

        this.renderer.render(this.scene, this.camera);
    }

    destroy() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }

        window.removeEventListener('resize', () => this.onWindowResize());

        this.clearGraph();

        if (this.particles) {
            this.scene.remove(this.particles);
            this.particles.geometry.dispose();
            this.particles.material.dispose();
        }

        this.renderer.dispose();
        this.container.removeChild(this.renderer.domElement);
    }

    // 获取可用主题列表
    getAvailableThemes() {
        return Object.entries(this.themes).map(([key, theme]) => ({
            id: key,
            name: theme.name
        }));
    }

    // 相机飞向节点
    flyToNode(nodeId) {
        const node = this.nodeObjects.get(nodeId);
        if (!node) return;

        const targetPos = node.position.clone();
        const duration = 1000; // 1秒
        const startPos = this.camera.position.clone();
        const startTime = Date.now();

        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = this.easeInOutCubic(progress);

            this.camera.position.lerpVectors(startPos, targetPos.clone().add(new THREE.Vector3(0, 20, 30)), eased);
            this.controls.target.lerp(targetPos, eased);

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                this.selectNode(node);
            }
        };

        animate();
    }

    easeInOutCubic(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    // 重置相机位置
    resetCamera() {
        this.camera.position.set(0, 20, 40);
        this.controls.target.set(0, 0, 0);
        this.deselectNode();
    }
}

// 导出为全局变量
window.SocialGraph3D = SocialGraph3D;
