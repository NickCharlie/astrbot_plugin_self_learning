// 自学习插件管理后台 - ECharts可视化大屏

// 登录状态检查
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/config');
        if (response.status === 401) {
            window.location.href = '/api/login';
            return false;
        }
        return true;
    } catch (error) {
        console.error('检查认证状态失败:', error);
        return false;
    }
}

// 登出功能
async function logout() {
    try {
        const response = await fetch('/api/logout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            window.location.href = '/api/login';
        } else {
            console.error('登出失败');
        }
    } catch (error) {
        console.error('登出请求失败:', error);
    }
}

// 全局变量
let currentConfig = {};
let currentMetrics = {};
let chartInstances = {};
let socialRelationsRefreshInterval = null; // 社交关系页面自动刷新定时器
const BUG_DEFAULT_MAX_IMAGES = 6;
const BUG_DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024;
let bugAssistantState = {
    config: null,
    uploadedFiles: [],
    pastedFiles: [],
    submitting: false,
    formInitialized: false
};

/**
 * 启动社交关系自动刷新
 * 注意：此函数需要在文件顶部定义，确保在loadPageData调用之前可用
 */
function startSocialRelationsAutoRefresh() {
    if (!socialRelationsRefreshInterval) {
        socialRelationsRefreshInterval = setInterval(() => {
            // 使用延迟检查确保变量已初始化
            if (typeof currentGroupId !== 'undefined' && currentGroupId &&
                document.getElementById('social-relations-page')?.classList.contains('active')) {
                const groupNameElement = document.getElementById('current-group-name');
                const groupName = groupNameElement?.textContent.replace(' 的成员关系', '') || '';
                if (groupName && typeof loadGroupRelations === 'function') {
                    loadGroupRelations(currentGroupId, groupName);
                }
            }
        }, 30000); // 每30秒刷新一次
        console.log('社交关系自动刷新已启动');
    }
}

/**
 * 停止社交关系自动刷新
 */
function stopSocialRelationsAutoRefresh() {
    if (socialRelationsRefreshInterval) {
        clearInterval(socialRelationsRefreshInterval);
        socialRelationsRefreshInterval = null;
        console.log('社交关系自动刷新已停止');
    }
}

/**
 * 智能文本差异高亮函数 - 改进版
 * 高亮key_change的内容(通常是拼接在原文本后的新内容)
 * @param {string} originalText - 原始文本
 * @param {string} proposedText - 建议更新的文本 (原文 + key_change)
 * @param {boolean} isKeyChangeOnly - 是否只是key_change片段
 * @returns {string} 带有HTML标记的高亮文本
 */
function highlightTextDifferences(originalText, proposedText, isKeyChangeOnly = false) {
    if (!originalText || !proposedText) {
        // 转换换行符为<br>以便正确显示
        return formatNewlines(escapeHtml(proposedText || ''));
    }

    // 如果是key_change片段，直接高亮整个新内容
    if (isKeyChangeOnly) {
        return `<span class="text-diff-new">${formatNewlines(escapeHtml(proposedText))}</span>`;
    }

    // 检测proposedText是否包含originalText作为前缀
    // 这种情况下，proposedText = originalText + keyChange
    if (proposedText.startsWith(originalText)) {
        // 提取keyChange部分
        const keyChange = proposedText.substring(originalText.length);

        if (keyChange.trim()) {
            // 高亮keyChange部分，保持原文不变
            return formatNewlines(escapeHtml(originalText)) +
                   `<span class="text-diff-new">${formatNewlines(escapeHtml(keyChange))}</span>`;
        }
        // 如果keyChange为空，说明内容完全相同
        return formatNewlines(escapeHtml(proposedText));
    }

    // 按行处理
    const originalLines = originalText.split('\n');
    const proposedLines = proposedText.split('\n');

    const highlightedLines = proposedLines.map((proposedLine, lineIndex) => {
        const trimmedProposed = proposedLine.trim();

        // 跳过空行
        if (!trimmedProposed) {
            return '';
        }

        // 找到最相似的原始行
        let mostSimilarOriginalLine = '';
        let maxSimilarity = 0;

        for (const originalLine of originalLines) {
            const similarity = calculateSimilarity(originalLine.trim(), trimmedProposed);
            if (similarity > maxSimilarity) {
                maxSimilarity = similarity;
                mostSimilarOriginalLine = originalLine.trim();
            }
        }

        // 如果相似度很低(< 0.3),说明是全新内容,高亮整行
        if (maxSimilarity < 0.3) {
            return `<span class="text-diff-new">${escapeHtml(proposedLine)}</span>`;
        }

        // 如果完全相同,不高亮
        if (maxSimilarity > 0.95) {
            return escapeHtml(proposedLine);
        }

        // 否则,进行词级别的差异高亮
        return highlightWordDifferences(mostSimilarOriginalLine, proposedLine);
    });

    return highlightedLines.join('<br>');  // 使用<br>而不是\n
}

/**
 * 格式化换行符为HTML换行
 * @param {string} text - 原始文本
 * @returns {string} 格式化后的HTML文本
 */
function formatNewlines(text) {
    if (!text) return '';
    // 将\n转换为<br>
    return text.replace(/\n/g, '<br>');
}

/**
 * 计算两个字符串的相似度(0-1之间)
 */
function calculateSimilarity(str1, str2) {
    if (str1 === str2) return 1.0;
    if (!str1 || !str2) return 0.0;

    // 使用简单的词集合相似度
    const words1 = new Set(str1.split(/\s+/));
    const words2 = new Set(str2.split(/\s+/));

    const intersection = new Set([...words1].filter(x => words2.has(x)));
    const union = new Set([...words1, ...words2]);

    return intersection.size / union.size;
}

/**
 * 词级别差异高亮
 */
function highlightWordDifferences(originalLine, proposedLine) {
    // 将原始行的词汇转为集合
    const originalWords = new Set(originalLine.split(/\s+/).filter(w => w.length > 0));

    // 分词并处理建议行
    const proposedTokens = proposedLine.split(/(\s+)/); // 保留空格

    let result = '';
    let consecutiveNewWords = [];

    for (let i = 0; i < proposedTokens.length; i++) {
        const token = proposedTokens[i];

        // 如果是空白字符,直接添加
        if (/^\s+$/.test(token)) {
            // 如果有积累的新词,先输出
            if (consecutiveNewWords.length > 0) {
                result += `<span class="text-diff-new">${escapeHtml(consecutiveNewWords.join(''))}</span>`;
                consecutiveNewWords = [];
            }
            result += token;
            continue;
        }

        // 检查这个词是否在原始文本中
        if (!originalWords.has(token)) {
            // 新词或修改的词,累积起来
            consecutiveNewWords.push(token);
        } else {
            // 如果有积累的新词,先输出
            if (consecutiveNewWords.length > 0) {
                result += `<span class="text-diff-new">${escapeHtml(consecutiveNewWords.join(''))}</span>`;
                consecutiveNewWords = [];
            }
            // 输出原有的词
            result += escapeHtml(token);
        }
    }

    // 处理末尾可能剩余的新词
    if (consecutiveNewWords.length > 0) {
        result += `<span class="text-diff-new">${escapeHtml(consecutiveNewWords.join(''))}</span>`;
    }

    return result;
}


/**
 * 转义HTML特殊字符
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ECharts Google Material Design 主题
const materialTheme = {
    color: ['#1976d2', '#4caf50', '#ff9800', '#f44336', '#9c27b0', '#00bcd4', '#795548', '#607d8b'],
    backgroundColor: 'transparent',
    textStyle: {
        fontFamily: 'Roboto, sans-serif',
        fontSize: 12,
        color: '#424242'
    },
    title: {
        textStyle: {
            fontFamily: 'Roboto, sans-serif',
            fontSize: 16,
            fontWeight: 500,
            color: '#212121'
        }
    },
    legend: {
        textStyle: {
            fontFamily: 'Roboto, sans-serif',
            fontSize: 12,
            color: '#757575'
        }
    },
    categoryAxis: {
        axisLine: { lineStyle: { color: '#e0e0e0' } },
        axisTick: { lineStyle: { color: '#e0e0e0' } },
        axisLabel: { color: '#757575' },
        splitLine: { lineStyle: { color: '#f5f5f5' } }
    },
    valueAxis: {
        axisLine: { lineStyle: { color: '#e0e0e0' } },
        axisTick: { lineStyle: { color: '#e0e0e0' } },
        axisLabel: { color: '#757575' },
        splitLine: { lineStyle: { color: '#f5f5f5' } }
    },
    grid: {
        borderColor: '#e0e0e0'
    }
};

// 初始化应用
document.addEventListener('DOMContentLoaded', async () => {
    console.log('自学习插件管理后台加载中...');
    
    // 首先检查认证状态
    const isAuthenticated = await checkAuthStatus();
    if (!isAuthenticated) {
        return; // 如果未认证，停止加载
    }
    
    // 绑定登出按钮事件
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
    
    // 绑定重新学习按钮事件
    const relearnBtn = document.getElementById('relearnBtn');
    if (relearnBtn) {
        relearnBtn.addEventListener('click', triggerRelearn);
    }
    
    // 注册ECharts主题
    echarts.registerTheme('material', materialTheme);
    
    // 初始化菜单导航
    initializeNavigation();
    
    // 加载初始数据
    await loadInitialData();
    
    // 初始化可视化大屏
    initializeDashboard();
    
    // 设置定时刷新
    setInterval(refreshDashboard, 5000); // 每5秒刷新一次
    
    console.log('管理后台初始化完成');
});

// 初始化导航菜单
function initializeNavigation() {
    const menuItems = document.querySelectorAll('.menu-item');
    const pages = document.querySelectorAll('.page');
    
    menuItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetPage = item.getAttribute('data-page');
            
            // 更新菜单状态
            menuItems.forEach(mi => mi.classList.remove('active'));
            item.classList.add('active');
            
            // 显示对应页面
            pages.forEach(page => page.classList.remove('active'));
            const targetPageElement = document.getElementById(targetPage + '-page');
            if (targetPageElement) {
                targetPageElement.classList.add('active');
            }
            
            // 更新页面标题和面包屑
            const pageTitle = item.querySelector('span').textContent;
            document.getElementById('page-title').textContent = pageTitle;
            document.getElementById('current-page').textContent = pageTitle;
            
            // 加载页面数据
            loadPageData(targetPage);
        });
    });
    
    // 初始化范围滑块事件监听
    initializeRangeSliders();
}

// 初始化范围滑块
function initializeRangeSliders() {
    document.querySelectorAll('input[type="range"]').forEach(slider => {
        const updateDisplay = () => {
            const valueSpan = slider.parentElement.querySelector('.range-value');
            if (valueSpan) {
                let displayValue = slider.value;
                
                // 根据不同的滑块类型格式化显示值
                if (slider.id.includes('Hour')) {
                    if (slider.id === 'moodChangeHour') {
                        displayValue = `${slider.value}:00`;
                    } else {
                        displayValue = `${slider.value} 小时`;
                    }
                } else if (slider.id.includes('Days')) {
                    displayValue = `${slider.value} 天`;
                } else if (slider.id.includes('Threshold') || slider.id.includes('Rate')) {
                    displayValue = parseFloat(slider.value).toFixed(2);
                } else if (slider.id.includes('Length')) {
                    displayValue = `${slider.value} 字符`;
                } else if (slider.id.includes('Messages') || slider.id.includes('Size') || slider.id.includes('Sample')) {
                    displayValue = `${slider.value} 条`;
                } else if (slider.id.includes('Dialogs') || slider.id.includes('Backups')) {
                    displayValue = `${slider.value} 个`;
                } else {
                    displayValue = slider.value;
                }
                
                valueSpan.textContent = displayValue;
                valueSpan.classList.add('range-updated');
                setTimeout(() => valueSpan.classList.remove('range-updated'), 300);
            }
        };
        
        slider.addEventListener('input', updateDisplay);
        slider.addEventListener('change', updateDisplay);
        
        // 初始化显示值
        updateDisplay();
    });
}

// 加载初始数据
async function loadInitialData() {
    updateRefreshIndicator('加载中...');
    try {
        await Promise.all([
            loadConfig(),
            loadMetrics(),
            loadPersonaUpdates(),
            loadLearningStatus()
        ]);
        
        updateRefreshIndicator('刚刚更新');
    } catch (error) {
        console.error('加载初始数据失败:', error);
        showError('加载数据失败，请刷新页面重试');
        updateRefreshIndicator('更新失败');
    }
}

// 初始化可视化大屏
function initializeDashboard() {
    // 渲染概览统计
    renderOverviewStats();
    
    // 初始化所有图表
    initializeCharts();
    
    // 绑定控件事件
    bindChartControls();
}

// 渲染概览统计
function renderOverviewStats() {
    const stats = currentMetrics;

    // 更新统计数字
    document.getElementById('total-messages').textContent = formatNumber(stats.total_messages_collected || 0);
    document.getElementById('filtered-messages').textContent = formatNumber(stats.filtered_messages || 0);

    // 计算总LLM调用次数
    const totalLLMCalls = Object.values(stats.llm_calls || {}).reduce((sum, model) => sum + (model.total_calls || 0), 0);
    document.getElementById('total-llm-calls').textContent = formatNumber(totalLLMCalls);

    // 使用学习会话统计的真实数据
    const learningSessionsCount = stats.learning_sessions?.active_sessions || 0;
    document.getElementById('learning-sessions').textContent = formatNumber(learningSessionsCount);

    // 更新学习效率显示 - 使用智能计算结果
    const learningEfficiencyElement = document.getElementById('learning-efficiency');
    if (learningEfficiencyElement && stats.learning_efficiency !== undefined) {
        learningEfficiencyElement.textContent = `效率: ${Math.round(stats.learning_efficiency)}%`;

        // 如果有详细数据，添加tooltip
        if (stats.learning_efficiency_details) {
            const details = stats.learning_efficiency_details;
            const tooltip = `
筛选率: ${Math.round(details.message_filter_rate)}%
提炼质量: ${Math.round(details.content_refine_quality)}%
风格进度: ${Math.round(details.style_learning_progress)}%
人格质量: ${Math.round(details.persona_update_quality)}%
激活策略: ${details.active_strategies_count}个
            `.trim();
            learningEfficiencyElement.title = tooltip;
        }
    }

    // 加载并显示真实的趋势百分比
    fetch('/api/metrics/trends')
        .then(response => response.json())
        .then(trendsData => {
            // 更新趋势指标（使用正确的ID）
            updateTrendIndicator('messages-trend', trendsData.message_growth);
            updateTrendIndicator('filtered-trend', trendsData.filtered_growth);
            updateTrendIndicator('llm-trend', trendsData.llm_growth);
            updateTrendIndicator('sessions-trend', trendsData.sessions_growth);
        })
        .catch(error => {
            console.error('加载趋势数据失败:', error);
            // 趋势数据加载失败时显示0%
            updateTrendIndicator('messages-trend', 0);
            updateTrendIndicator('filtered-trend', 0);
            updateTrendIndicator('llm-trend', 0);
            updateTrendIndicator('sessions-trend', 0);
        });
}

// 更新趋势指示器
function updateTrendIndicator(elementId, percentage) {
    const element = document.getElementById(elementId);
    if (element) {
        const isPositive = percentage >= 0;
        const symbol = isPositive ? '+' : '';
        const color = isPositive ? '#4caf50' : '#f44336';
        
        element.textContent = `${symbol}${percentage}%`;
        element.style.color = color;
        
        // 更新图标
        const icon = element.parentElement.querySelector('.material-icons');
        if (icon) {
            icon.textContent = isPositive ? 'trending_up' : 'trending_down';
            icon.style.color = color;
        }
    }
}

// 初始化图表
function initializeCharts() {
    // LLM使用分布饼图
    initializeLLMUsagePie();
    
    // 消息处理趋势线图
    initializeMessageTrendLine();
    
    // LLM响应时间柱状图
    initializeResponseTimeBar();
    
    // 学习进度仪表盘
    initializeLearningProgressGauge();
    
    // 系统状态雷达图
    initializeSystemStatusRadar();
    
    // 对话风格学习可视化
    initializeStyleLearningDashboard();
    
    // 用户活跃度热力图
    initializeActivityHeatmap();
}

// LLM使用分布饼图
function initializeLLMUsagePie() {
    const chartDom = document.getElementById('llm-usage-pie');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['llm-usage-pie'] = chart;
    
    const llmData = currentMetrics.llm_calls || {};
    const data = Object.entries(llmData).map(([model, stats]) => ({
        name: model,
        value: stats.total_calls || 0
    }));
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{a} <br/>{b}: {c} ({d}%)'
        },
        legend: {
            bottom: '5%',
            left: 'center'
        },
        series: [
            {
                name: 'LLM调用分布',
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '45%'],
                data: data,
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                },
                label: {
                    show: true,
                    formatter: '{b}: {c}'
                },
                labelLine: {
                    show: true
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 消息处理趋势线图
function initializeMessageTrendLine() {
    const chartDom = document.getElementById('message-trend-line');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['message-trend-line'] = chart;
    
    // 优先使用真实数据，失败时使用空数据而非模拟数据
    fetch('/api/analytics/trends')
        .then(response => response.json())
        .then(data => {
            const hourlyData = data.hourly_trends || [];
            const hours = hourlyData.map(item => item.time);
            const rawMessages = hourlyData.map(item => item.raw_messages);
            const filteredMessages = hourlyData.map(item => item.filtered_messages);
            
            const option = {
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross'
                    }
                },
                legend: {
                    data: ['原始消息', '筛选消息']
                },
                xAxis: {
                    type: 'category',
                    data: hours,
                    boundaryGap: false
                },
                yAxis: {
                    type: 'value'
                },
                series: [
                    {
                        name: '原始消息',
                        type: 'line',
                        data: rawMessages,
                        smooth: true,
                        itemStyle: { color: '#2196f3' },
                        areaStyle: { opacity: 0.3 }
                    },
                    {
                        name: '筛选消息',
                        type: 'line',
                        data: filteredMessages,
                        smooth: true,
                        itemStyle: { color: '#4caf50' },
                        areaStyle: { opacity: 0.3 }
                    }
                ]
            };
            
            chart.setOption(option);
        })
        .catch(error => {
            console.error('加载趋势数据失败:', error);
            // 显示空图表而不是模拟数据
            initializeEmptyMessageTrendLine(chart);
        });
}

// 空数据的消息趋势图
function initializeEmptyMessageTrendLine(chart) {
    const hours = [];
    for (let i = 23; i >= 0; i--) {
        const hour = new Date(Date.now() - i * 60 * 60 * 1000);
        hours.push(hour.getHours() + ':00');
    }
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            }
        },
        legend: {
            data: ['原始消息', '筛选消息']
        },
        xAxis: {
            type: 'category',
            data: hours,
            boundaryGap: false
        },
        yAxis: {
            type: 'value'
        },
        series: [
            {
                name: '原始消息',
                type: 'line',
                data: new Array(24).fill(0),
                smooth: true,
                itemStyle: { color: '#2196f3' }
            },
            {
                name: '筛选消息',
                type: 'line',
                data: new Array(24).fill(0),
                smooth: true,
                itemStyle: { color: '#4caf50' }
            }
        ]
    };
    
    chart.setOption(option);
}

// LLM响应时间柱状图
function initializeResponseTimeBar() {
    const chartDom = document.getElementById('response-time-bar');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['response-time-bar'] = chart;
    
    const llmData = currentMetrics.llm_calls || {};
    const models = Object.keys(llmData);
    const responseTimes = Object.values(llmData).map(stats => stats.avg_response_time_ms || 0);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: '{b}<br/>{a}: {c}ms'
        },
        xAxis: {
            type: 'category',
            data: models,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: {
            type: 'value',
            name: '响应时间(ms)'
        },
        series: [
            {
                name: '平均响应时间',
                type: 'bar',
                data: responseTimes,
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#1976d2' },
                        { offset: 1, color: '#64b5f6' }
                    ])
                },
                markLine: {
                    data: [
                        { type: 'average', name: '平均值' }
                    ]
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 学习进度仪表盘
function initializeLearningProgressGauge() {
    const chartDom = document.getElementById('learning-progress-gauge');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['learning-progress-gauge'] = chart;

    // 计算学习效率 - 优先使用智能计算结果
    const totalMessages = currentMetrics.total_messages_collected || 0;
    const filteredMessages = currentMetrics.filtered_messages || 0;

    // 使用智能计算的学习效率，如果不存在则回退到简单计算
    let efficiency = 0;
    if (currentMetrics.learning_efficiency !== undefined) {
        efficiency = currentMetrics.learning_efficiency;
    } else {
        efficiency = totalMessages > 0 ? (filteredMessages / totalMessages * 100) : 0;
    }

    // 如果有详细的学习效率数据，在控制台输出
    if (currentMetrics.learning_efficiency_details) {
        console.log('学习效率详情:', currentMetrics.learning_efficiency_details);
    }
    
    const option = {
        series: [
            {
                type: 'gauge',
                startAngle: 180,
                endAngle: 0,
                center: ['50%', '75%'],
                radius: '90%',
                min: 0,
                max: 100,
                splitNumber: 8,
                axisLine: {
                    lineStyle: {
                        width: 6,
                        color: [
                            [0.25, '#ff4444'],
                            [0.5, '#ff9800'],
                            [0.75, '#4caf50'],
                            [1, '#1976d2']
                        ]
                    }
                },
                pointer: {
                    icon: 'path://M12.8,0.7l12,40.1H0.7L12.8,0.7z',
                    length: '12%',
                    width: 20,
                    offsetCenter: [0, '-60%'],
                    itemStyle: {
                        color: 'auto'
                    }
                },
                axisTick: {
                    length: 12,
                    lineStyle: {
                        color: 'auto',
                        width: 2
                    }
                },
                splitLine: {
                    length: 20,
                    lineStyle: {
                        color: 'auto',
                        width: 5
                    }
                },
                axisLabel: {
                    color: '#464646',
                    fontSize: 10,
                    distance: -60,
                    formatter: function (value) {
                        if (value === 100) {
                            return '优秀';
                        } else if (value === 75) {
                            return '良好';
                        } else if (value === 50) {
                            return '一般';
                        } else if (value === 25) {
                            return '较差';
                        }
                        return '';
                    }
                },
                title: {
                    offsetCenter: [0, '-10%'],
                    fontSize: 16
                },
                detail: {
                    fontSize: 30,
                    offsetCenter: [0, '-35%'],
                    valueAnimation: true,
                    formatter: function (value) {
                        return Math.round(value) + '%';
                    },
                    color: 'auto'
                },
                data: [
                    {
                        value: efficiency.toFixed(1),
                        name: '学习效率'
                    }
                ]
            }
        ]
    };
    
    chart.setOption(option);
}

// 系统状态雷达图
function initializeSystemStatusRadar() {
    const chartDom = document.getElementById('system-status-radar');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['system-status-radar'] = chart;
    
    // 从当前指标计算真实的系统状态
    const stats = currentMetrics;
    
    // 消息抓取效率 (基于真实消息收集情况)
    const totalMessages = stats.total_messages_collected || 0;
    const messageCapture = totalMessages > 0 ? Math.min(100, (totalMessages / 1000) * 100) : 0;
    
    // 数据筛选质量 (基于筛选率)
    const filteredMessages = stats.filtered_messages || 0;
    const filteringQuality = totalMessages > 0 ? (filteredMessages / totalMessages) * 100 : 0;
    
    // LLM调用健康度 (基于成功率)
    const llmCalls = stats.llm_calls || {};
    const llmModels = Object.values(llmCalls);
    const avgSuccessRate = llmModels.length > 0 ? 
        llmModels.reduce((sum, model) => sum + (model.success_rate || 0), 0) / llmModels.length * 100 : 0;
    
    // 学习质量 (基于学习效率)
    const learningQuality = stats.learning_efficiency || 0;
    
    // 响应速度 (基于LLM平均响应时间，越快分数越高)
    const avgResponseTime = llmModels.length > 0 ? 
        llmModels.reduce((sum, model) => sum + (model.avg_response_time_ms || 0), 0) / llmModels.length : 2000;
    const responseSpeed = Math.max(0, 100 - (avgResponseTime / 20)); // 2000ms = 0分，0ms = 100分
    
    // 系统稳定性 (基于CPU和内存使用率)
    const systemMetrics = stats.system_metrics || {};
    const cpuHealth = Math.max(0, 100 - (systemMetrics.cpu_percent || 0));
    const memoryHealth = Math.max(0, 100 - (systemMetrics.memory_percent || 0));
    const systemStability = (cpuHealth + memoryHealth) / 2;
    
    const option = {
        tooltip: {
            formatter: '{b}: {c}%'
        },
        radar: {
            indicator: [
                { name: '消息抓取', max: 100 },
                { name: '数据筛选', max: 100 },
                { name: 'LLM调用', max: 100 },
                { name: '学习质量', max: 100 },
                { name: '响应速度', max: 100 },
                { name: '系统稳定性', max: 100 }
            ],
            center: ['50%', '50%'],
            radius: '75%'
        },
        series: [
            {
                name: '系统状态',
                type: 'radar',
                data: [
                    {
                        value: [
                            Math.round(messageCapture),
                            Math.round(filteringQuality),
                            Math.round(avgSuccessRate),
                            Math.round(learningQuality),
                            Math.round(responseSpeed),
                            Math.round(systemStability)
                        ],
                        name: '当前状态',
                        itemStyle: { color: '#1976d2' },
                        areaStyle: { opacity: 0.3 }
                    }
                ]
            }
        ]
    };
    
    chart.setOption(option);
}

// 对话风格学习可视化
function initializeStyleLearningDashboard() {
    const chartDom = document.getElementById('style-learning-dashboard');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['style-learning-dashboard'] = chart;
    
    // 获取风格学习数据
    fetch('/api/style_learning/results')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                // 显示获取失败状态
                initializeEmptyStyleLearningChart(chart, data.error);
                return;
            }
            
            const styleProgress = data.style_progress || [];
            
            if (styleProgress.length === 0) {
                initializeEmptyStyleLearningChart(chart, '暂无风格学习数据');
                return;
            }
            
            const styles = styleProgress.map(item => {
                // 使用 group_id 或者时间戳作为标签
                if (item.group_id) {
                    return `群组${item.group_id}`;
                } else if (item.timestamp) {
                    const date = new Date(item.timestamp * 1000);
                    return date.toLocaleDateString();
                }
                return '未知';
            });
            const confidenceData = styleProgress.map(item => {
                // quality_score 通常是 0-1 之间的值，转换为百分比
                return (item.quality_score || 0) * 100;
            });
            const sampleData = styleProgress.map(item => {
                // 使用 filtered_count 或 message_count 作为样本数量
                return item.filtered_count || item.message_count || item.total_samples || 0;
            });
            
            const option = {
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'cross'
                    }
                },
                legend: {
                    data: ['平均置信度(%)', '样本数量']
                },
                xAxis: {
                    type: 'category',
                    data: styles,
                    axisLabel: {
                        rotate: 45
                    }
                },
                yAxis: [
                    {
                        type: 'value',
                        name: '置信度(%)',
                        position: 'left',
                        max: 100
                    },
                    {
                        type: 'value',
                        name: '样本数量',
                        position: 'right'
                    }
                ],
                series: [
                    {
                        name: '平均置信度(%)',
                        type: 'bar',
                        data: confidenceData,
                        itemStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: '#667eea' },
                                { offset: 1, color: '#764ba2' }
                            ])
                        }
                    },
                    {
                        name: '样本数量',
                        type: 'line',
                        yAxisIndex: 1,
                        data: sampleData,
                        itemStyle: {
                            color: '#f093fb'
                        },
                        lineStyle: {
                            width: 3
                        }
                    }
                ]
            };
            
            chart.setOption(option);
        })
        .catch(error => {
            console.error('获取风格学习数据失败:', error);
            initializeEmptyStyleLearningChart(chart, '获取数据失败，请检查网络连接');
        });
}

// 空的风格学习图表
function initializeEmptyStyleLearningChart(chart, message) {
    const option = {
        title: {
            text: message || '暂无数据',
            left: 'center',
            top: 'middle',
            textStyle: {
                fontSize: 14,
                color: '#999'
            }
        },
        xAxis: {
            type: 'category',
            data: []
        },
        yAxis: {
            type: 'value'
        },
        series: [{
            name: '风格学习',
            type: 'bar',
            data: []
        }]
    };
    
    chart.setOption(option);
}

// 用户活跃度热力图
function initializeActivityHeatmap() {
    const chartDom = document.getElementById('activity-heatmap');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['activity-heatmap'] = chart;
    
    // 从API获取真实热力图数据
    fetch('/api/analytics/trends')
        .then(response => response.json())
        .then(data => {
            const heatmapData = data.activity_heatmap || {};
            const actualData = heatmapData.data || [];
            const days = heatmapData.days || ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
            const hours = heatmapData.hours || [];
            
            const option = {
                tooltip: {
                    position: 'top',
                    formatter: function (params) {
                        return `${days[params.value[1]]} ${hours[params.value[0]]}<br/>活跃度: ${params.value[2]}`;
                    }
                },
                grid: {
                    height: '50%',
                    top: '10%'
                },
                xAxis: {
                    type: 'category',
                    data: hours,
                    splitArea: {
                        show: true
                    }
                },
                yAxis: {
                    type: 'category',
                    data: days,
                    splitArea: {
                        show: true
                    }
                },
                visualMap: {
                    min: 0,
                    max: Math.max(...actualData.map(item => item[2]), 10), // 动态设置最大值
                    calculable: true,
                    orient: 'horizontal',
                    left: 'center',
                    bottom: '15%',
                    inRange: {
                        color: ['#e3f2fd', '#1976d2']
                    }
                },
                series: [
                    {
                        name: '活跃度',
                        type: 'heatmap',
                        data: actualData,
                        label: {
                            show: false
                        },
                        emphasis: {
                            itemStyle: {
                                shadowBlur: 10,
                                shadowColor: 'rgba(0, 0, 0, 0.5)'
                            }
                        }
                    }
                ]
            };
            
            chart.setOption(option);
        })
        .catch(error => {
            console.error('加载活跃度数据失败:', error);
            // 使用空数据而不是模拟数据
            initializeEmptyActivityHeatmap(chart);
        });
}

// 空活跃度热力图
function initializeEmptyActivityHeatmap(chart) {
    const hours = [];
    const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    for (let i = 0; i < 24; i++) {
        hours.push(i + ':00');
    }
    
    const data = [];
    for (let i = 0; i < 7; i++) {
        for (let j = 0; j < 24; j++) {
            data.push([j, i, 0]); // 全部设为0
        }
    }
    
    const option = {
        tooltip: {
            position: 'top',
            formatter: function (params) {
                return `${days[params.value[1]]} ${hours[params.value[0]]}<br/>活跃度: ${params.value[2]}`;
            }
        },
        grid: {
            height: '50%',
            top: '10%'
        },
        xAxis: {
            type: 'category',
            data: hours,
            splitArea: {
                show: true
            }
        },
        yAxis: {
            type: 'category',
            data: days,
            splitArea: {
                show: true
            }
        },
        visualMap: {
            min: 0,
            max: 10,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: '15%',
            inRange: {
                color: ['#e3f2fd', '#1976d2']
            }
        },
        series: [
            {
                name: '活跃度',
                type: 'heatmap',
                data: data,
                label: {
                    show: false
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 绑定图表控件事件
function bindChartControls() {
    // LLM时间范围选择器
    document.getElementById('llm-time-range').addEventListener('change', (e) => {
        updateLLMUsageChart(e.target.value);
    });
    
    // 消息时间范围选择器
    document.getElementById('message-time-range').addEventListener('change', (e) => {
        updateMessageTrendChart(e.target.value);
    });
    
    // 活跃度时间按钮
    document.querySelectorAll('.time-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            // 更新按钮状态
            document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            // 更新热力图
            updateActivityHeatmap(e.target.dataset.period);
        });
    });
    
    // 配置保存按钮
    const saveBtn = document.getElementById('saveConfig');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveConfiguration);
    }
    
    // 配置重置按钮
    const resetBtn = document.getElementById('resetConfig');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetConfiguration);
    }
}

// 加载配置数据
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            currentConfig = await response.json();
            renderConfigPage();
        } else {
            throw new Error('加载配置失败');
        }
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

// 加载性能指标
async function loadMetrics() {
    try {
        const response = await fetch('/api/metrics');
        if (response.ok) {
            currentMetrics = await response.json();
        } else {
            throw new Error('加载性能指标失败');
        }
    } catch (error) {
        console.error('加载性能指标失败:', error);
    }
}

// 人格审查分页和筛选状态
let allPersonaUpdates = [];  // 存储所有数据
let filteredPersonaUpdates = [];  // 存储筛选后的数据
let pendingCurrentPage = 1;
let pendingPageSize = 20;

// 加载人格更新数据
async function loadPersonaUpdates() {
    try {
        console.log('[DEBUG] 开始加载人格更新数据...');

        // 显示加载指示器
        const reviewList = document.getElementById('review-list');
        if (reviewList) {
            reviewList.innerHTML = '<div class="loading-indicator" style="text-align: center; padding: 40px;"><i class="material-icons rotating" style="font-size: 48px; color: #4CAF50;">refresh</i><p>正在加载人格审查记录...</p></div>';
        }

        const response = await fetch('/api/persona_updates');
        console.log('[DEBUG] API响应状态:', response.status);

        if (response.ok) {
            const data = await response.json();
            console.log('[DEBUG] 接收到的数据:', data);

            // 确保 data 有正确的结构
            if (data && data.success && Array.isArray(data.updates)) {
                console.log('[DEBUG] 数据格式正确, 记录数量:', data.updates.length);
                allPersonaUpdates = data.updates;

                // 更新群组筛选选项
                updateGroupFilterOptions(data.updates);

                // 应用筛选
                console.log('[DEBUG] 应用筛选前, allPersonaUpdates:', allPersonaUpdates.length);
                applyPersonaFilters();
                console.log('[DEBUG] 应用筛选后, filteredPersonaUpdates:', filteredPersonaUpdates.length);

                await updateReviewStats(data.updates);
            } else {
                console.error('[DEBUG] 人格更新数据格式不正确:', data);
                allPersonaUpdates = [];
                filteredPersonaUpdates = [];
                renderPersonaUpdates([]);
                await updateReviewStats([]);
            }
        } else {
            throw new Error('加载人格更新失败');
        }
    } catch (error) {
        console.error('[DEBUG] 加载人格更新失败:', error);
        // 确保即使出错也能正常渲染空列表
        allPersonaUpdates = [];
        filteredPersonaUpdates = [];

        // 显示错误信息
        const reviewList = document.getElementById('review-list');
        if (reviewList) {
            reviewList.innerHTML = '<div class="no-updates" style="color: #f44336;">加载失败，请刷新页面重试</div>';
        }

        await updateReviewStats([]);
    }
}

// 更新群组筛选选项
function updateGroupFilterOptions(updates) {
    const groupSelect = document.getElementById('filter-group');
    if (!groupSelect) return;

    // 获取所有唯一的群组ID
    const groups = [...new Set(updates.map(u => u.group_id).filter(g => g))];

    // 保留第一个选项，清除其他
    groupSelect.innerHTML = '<option value="">全部群组</option>';

    groups.forEach(group => {
        const option = document.createElement('option');
        option.value = group;
        option.textContent = group;
        groupSelect.appendChild(option);
    });
}

// 应用筛选条件
function applyPersonaFilters() {
    const typeFilter = document.getElementById('filter-type')?.value || '';
    const groupFilter = document.getElementById('filter-group')?.value || '';
    const confidenceFilter = document.getElementById('filter-confidence')?.value || '';
    const timeFilter = document.getElementById('filter-time')?.value || '';

    filteredPersonaUpdates = allPersonaUpdates.filter(update => {
        // 类型筛选 - 使用 review_source 字段进行精确匹配
        if (typeFilter) {
            const reviewSource = update.review_source || '';

            // 精确匹配 review_source
            if (typeFilter === 'style_learning' && reviewSource !== 'style_learning') return false;
            if (typeFilter === 'persona_learning' && reviewSource !== 'persona_learning') return false;
            if (typeFilter === 'traditional' && reviewSource !== 'traditional') return false;
        }

        // 群组筛选
        if (groupFilter && update.group_id !== groupFilter) return false;

        // 置信度筛选
        if (confidenceFilter) {
            const confidence = update.confidence_score || 0;
            if (confidenceFilter === 'high' && confidence < 0.8) return false;
            if (confidenceFilter === 'medium' && (confidence < 0.5 || confidence >= 0.8)) return false;
            if (confidenceFilter === 'low' && confidence >= 0.5) return false;
        }

        // 时间筛选
        if (timeFilter) {
            const timestamp = update.timestamp || 0;
            const now = Date.now() / 1000;
            const dayInSeconds = 86400;

            if (timeFilter === 'today') {
                const todayStart = Math.floor(now / dayInSeconds) * dayInSeconds;
                if (timestamp < todayStart) return false;
            } else if (timeFilter === 'week' && now - timestamp > 7 * dayInSeconds) {
                return false;
            } else if (timeFilter === 'month' && now - timestamp > 30 * dayInSeconds) {
                return false;
            }
        }

        return true;
    });

    // 重置到第一页
    pendingCurrentPage = 1;

    // 渲染分页数据
    renderPaginatedPersonaUpdates();
}

// 重置筛选条件
function resetPersonaFilters() {
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-group').value = '';
    document.getElementById('filter-confidence').value = '';
    document.getElementById('filter-time').value = '';
    applyPersonaFilters();
}

// 渲染分页后的数据
function renderPaginatedPersonaUpdates() {
    console.log('[DEBUG] renderPaginatedPersonaUpdates 被调用');
    const totalCount = filteredPersonaUpdates.length;
    console.log('[DEBUG] filteredPersonaUpdates总数:', totalCount);

    const totalPages = Math.ceil(totalCount / pendingPageSize) || 1;

    // 确保当前页在有效范围内
    if (pendingCurrentPage > totalPages) pendingCurrentPage = totalPages;
    if (pendingCurrentPage < 1) pendingCurrentPage = 1;

    const startIndex = (pendingCurrentPage - 1) * pendingPageSize;
    const endIndex = Math.min(startIndex + pendingPageSize, totalCount);
    const pageData = filteredPersonaUpdates.slice(startIndex, endIndex);

    console.log('[DEBUG] 分页数据:', {
        startIndex,
        endIndex,
        pageDataLength: pageData.length,
        currentPage: pendingCurrentPage,
        totalPages
    });

    // 渲染列表
    renderPersonaUpdates(pageData);

    // 更新分页控件
    updatePaginationControls(startIndex, endIndex, totalCount, totalPages);
}

// 更新分页控件状态
function updatePaginationControls(startIndex, endIndex, totalCount, totalPages) {
    const showingStart = document.getElementById('pending-showing-start');
    const showingEnd = document.getElementById('pending-showing-end');
    const totalCountEl = document.getElementById('pending-total-count');
    const currentPageEl = document.getElementById('pending-current-page');
    const totalPagesEl = document.getElementById('pending-total-pages');
    const prevBtn = document.getElementById('pending-prev-btn');
    const nextBtn = document.getElementById('pending-next-btn');

    if (showingStart) showingStart.textContent = totalCount > 0 ? startIndex + 1 : 0;
    if (showingEnd) showingEnd.textContent = endIndex;
    if (totalCountEl) totalCountEl.textContent = totalCount;
    if (currentPageEl) currentPageEl.textContent = pendingCurrentPage;
    if (totalPagesEl) totalPagesEl.textContent = totalPages;

    if (prevBtn) prevBtn.disabled = pendingCurrentPage <= 1;
    if (nextBtn) nextBtn.disabled = pendingCurrentPage >= totalPages;
}

// 切换页面
function changePendingPage(delta) {
    pendingCurrentPage += delta;
    renderPaginatedPersonaUpdates();
}

// 改变每页显示数量
function changePendingPageSize() {
    const pageSizeSelect = document.getElementById('pending-page-size');
    if (pageSizeSelect) {
        pendingPageSize = parseInt(pageSizeSelect.value, 10);
        pendingCurrentPage = 1;  // 重置到第一页
        renderPaginatedPersonaUpdates();
    }
}

// 加载学习状态
async function loadLearningStatus() {
    try {
        // 模拟学习状态数据
        const mockStatus = {
            current_session: {
                session_id: 'sess_' + Date.now(),
                start_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toLocaleString(),
                messages_processed: Math.floor(Math.random() * 100) + 50,
                status: Math.random() > 0.5 ? 'active' : 'stopped'
            }
        };
        
        renderLearningStatus(mockStatus);
    } catch (error) {
        console.error('加载学习状态失败:', error);
    }
}

// 渲染配置页面
function renderConfigPage() {
    // 基础开关
    document.getElementById('enableMessageCapture').checked = currentConfig.enable_message_capture || false;
    document.getElementById('enableAutoLearning').checked = currentConfig.enable_auto_learning || false;
    document.getElementById('enableRealtimeLearning').checked = currentConfig.enable_realtime_learning || false;
    document.getElementById('enableRealtimeLLMFilter').checked = currentConfig.enable_realtime_llm_filter || false;
    document.getElementById('enableWebInterface').checked = currentConfig.enable_web_interface || true;
    document.getElementById('webInterfacePort').value = currentConfig.web_interface_port || 7833;
    
    // MaiBot增强功能
    document.getElementById('enableMaibotFeatures').checked = currentConfig.enable_maibot_features || true;
    document.getElementById('enableExpressionPatterns').checked = currentConfig.enable_expression_patterns || true;
    document.getElementById('enableMemoryGraph').checked = currentConfig.enable_memory_graph || true;
    document.getElementById('enableKnowledgeGraph').checked = currentConfig.enable_knowledge_graph || true;
    document.getElementById('enableTimeDecay').checked = currentConfig.enable_time_decay || true;
    
    // 目标设置
    if (currentConfig.target_qq_list) {
        document.getElementById('targetQQList').value = currentConfig.target_qq_list.join(', ');
    }
    if (currentConfig.target_blacklist) {
        document.getElementById('targetBlacklist').value = currentConfig.target_blacklist.join(', ');
    }
    document.getElementById('currentPersonaName').value = currentConfig.current_persona_name || 'default';
    
    // LLM提供商
    document.getElementById('filterProviderId').value = currentConfig.filter_provider_id || '';
    document.getElementById('refineProviderId').value = currentConfig.refine_provider_id || '';
    document.getElementById('reinforceProviderId').value = currentConfig.reinforce_provider_id || '';
    
    // 学习参数
    document.getElementById('learningInterval').value = currentConfig.learning_interval_hours || 6;
    document.getElementById('minMessagesForLearning').value = currentConfig.min_messages_for_learning || 50;
    document.getElementById('maxMessagesPerBatch').value = currentConfig.max_messages_per_batch || 200;
    
    // 筛选参数
    document.getElementById('messageMinLength').value = currentConfig.message_min_length || 5;
    document.getElementById('messageMaxLength').value = currentConfig.message_max_length || 500;
    document.getElementById('confidenceThreshold').value = currentConfig.confidence_threshold || 0.7;
    document.getElementById('relevanceThreshold').value = currentConfig.relevance_threshold || 0.6;
    
    // 风格分析
    document.getElementById('styleAnalysisBatchSize').value = currentConfig.style_analysis_batch_size || 100;
    document.getElementById('styleUpdateThreshold').value = currentConfig.style_update_threshold || 0.6;
    
    // 机器学习设置
    document.getElementById('enableMLAnalysis').checked = currentConfig.enable_ml_analysis || true;
    document.getElementById('maxMLSampleSize').value = currentConfig.max_ml_sample_size || 100;
    document.getElementById('mlCacheTimeoutHours').value = currentConfig.ml_cache_timeout_hours || 1;
    
    // 人格备份
    document.getElementById('autoBackupEnabled').checked = currentConfig.auto_backup_enabled || true;
    document.getElementById('backupIntervalHours').value = currentConfig.backup_interval_hours || 24;
    document.getElementById('maxBackupsPerGroup').value = currentConfig.max_backups_per_group || 10;
    
    // 高级设置
    document.getElementById('debugMode').checked = currentConfig.debug_mode || false;
    document.getElementById('saveRawMessages').checked = currentConfig.save_raw_messages || true;
    document.getElementById('autoBackupIntervalDays').value = currentConfig.auto_backup_interval_days || 7;
    
    // PersonaUpdater配置
    document.getElementById('personaMergeStrategy').value = currentConfig.persona_merge_strategy || 'smart';
    document.getElementById('maxMoodImitationDialogs').value = currentConfig.max_mood_imitation_dialogs || 20;
    document.getElementById('enablePersonaEvolution').checked = currentConfig.enable_persona_evolution || true;
    document.getElementById('personaCompatibilityThreshold').value = currentConfig.persona_compatibility_threshold || 0.6;
    document.getElementById('autoApplyPersonaUpdates').checked = currentConfig.auto_apply_persona_updates || true;
    document.getElementById('personaUpdateBackupEnabled').checked = currentConfig.persona_update_backup_enabled || true;
    
    // 好感度系统
    document.getElementById('enableAffectionSystem').checked = currentConfig.enable_affection_system || true;
    document.getElementById('maxTotalAffection').value = currentConfig.max_total_affection || 250;
    document.getElementById('maxUserAffection').value = currentConfig.max_user_affection || 100;
    document.getElementById('affectionDecayRate').value = currentConfig.affection_decay_rate || 0.95;
    document.getElementById('dailyMoodChange').checked = currentConfig.daily_mood_change || true;
    document.getElementById('moodAffectAffection').checked = currentConfig.mood_affect_affection || true;
    
    // 情绪系统
    document.getElementById('enableDailyMood').checked = currentConfig.enable_daily_mood || true;
    document.getElementById('enableStartupRandomMood').checked = currentConfig.enable_startup_random_mood || true;
    document.getElementById('moodChangeHour').value = currentConfig.mood_change_hour || 6;
    document.getElementById('moodPersistenceHours').value = currentConfig.mood_persistence_hours || 24;
    
    // 刷新所有滑块的显示值
    document.querySelectorAll('input[type="range"]').forEach(slider => {
        const event = new Event('input');
        slider.dispatchEvent(event);
    });
}

// 渲染人格更新列表
function renderPersonaUpdates(updates) {
    console.log('[DEBUG] renderPersonaUpdates 被调用, updates数量:', updates.length);

    const reviewList = document.getElementById('review-list');

    if (!reviewList) {
        console.error('[DEBUG] 找不到 review-list 元素!');
        return;
    }

    console.log('[DEBUG] 找到 review-list 元素');

    if (!updates || updates.length === 0) {
        console.log('[DEBUG] updates为空,显示"暂无"提示');
        reviewList.innerHTML = '<div class="no-updates">暂无待审查的人格更新</div>';
        return;
    }

    // 清空列表
    reviewList.innerHTML = '';
    console.log('[DEBUG] 开始渲染', updates.length, '条记录');

    // 为每个更新创建元素并绑定事件
    updates.forEach((update, index) => {
        console.log('[DEBUG] 渲染第', index+1, '条记录, ID:', update.id);

        const updateElement = document.createElement('div');
        updateElement.className = 'persona-update-item';
        
        // 确定更新类型和对应的徽章 - 使用 review_source 字段
        const reviewSource = update.review_source || '';
        let typeBadge = '';
        let typeText = '';

        if (reviewSource === 'style_learning') {
            typeBadge = '<span class="type-badge style-badge">风格学习</span>';
            typeText = '风格学习更新';
        } else if (reviewSource === 'persona_learning') {
            typeBadge = '<span class="type-badge persona-badge">人格学习</span>';
            typeText = '人格学习更新';
        } else {
            typeBadge = '<span class="type-badge general-badge">常规更新</span>';
            typeText = '常规更新';
        }

        updateElement.innerHTML = `
            <div class="update-badges-row">
                ${typeBadge}
                <span class="id-badge">${update.id}</span>
            </div>
            <div class="update-header">
                <div class="update-checkbox">
                    <input type="checkbox" class="review-checkbox" value="${update.id}" id="review-${update.id}">
                    <label for="review-${update.id}"></label>
                </div>
                <div class="update-info">
                </div>
            </div>
            <div class="update-content">
                <p><strong>原因:</strong> ${update.reason || '未提供'}</p>
                <p><strong>时间:</strong> ${new Date(update.timestamp * 1000).toLocaleString()}</p>
                <p><strong>置信度:</strong> ${(update.confidence_score * 100).toFixed(1)}%</p>
                <div class="update-preview">
                    <p><strong>原始内容:</strong> <button class="toggle-content-btn" data-target="original-${update.id}">展开完整内容</button></p>
                    <div class="content-preview" id="original-${update.id}" data-collapsed="true">${truncateText(update.original_content || '', 200)}</div>
                    <div class="content-preview full-content" id="original-full-${update.id}" style="display: none;">${update.original_content || ''}</div>

                    <p><strong>建议更新:</strong> <button class="toggle-content-btn" data-target="proposed-${update.id}">展开完整内容</button></p>
                    <div class="content-preview highlighted-diff" id="proposed-${update.id}" data-collapsed="true"></div>
                    <div class="content-preview full-content highlighted-diff" id="proposed-full-${update.id}" style="display: none;"></div>
                </div>
            </div>
            <div class="update-actions">
                <button class="btn btn-primary edit-btn">
                    <i class="material-icons">edit</i>
                    编辑
                </button>
                <button class="btn btn-success approve-btn">
                    <i class="material-icons">check</i>
                    批准
                </button>
                <button class="btn btn-danger reject-btn">
                    <i class="material-icons">close</i>
                    拒绝
                </button>
                <button class="btn btn-secondary delete-btn">
                    <i class="material-icons">delete</i>
                    删除
                </button>
            </div>
        `;
        
        // 绑定事件处理器
        const editBtn = updateElement.querySelector('.edit-btn');
        const approveBtn = updateElement.querySelector('.approve-btn');
        const rejectBtn = updateElement.querySelector('.reject-btn');
        const deleteBtn = updateElement.querySelector('.delete-btn');
        const toggleBtns = updateElement.querySelectorAll('.toggle-content-btn');
        
        editBtn.addEventListener('click', () => editPersonaUpdate(update.id));
        approveBtn.addEventListener('click', () => reviewUpdate(update.id, 'approve'));
        rejectBtn.addEventListener('click', () => reviewUpdate(update.id, 'reject'));
        deleteBtn.addEventListener('click', () => deletePersonaUpdate(update.id));
        
        // 添加复选框变化监听器
        const checkbox = updateElement.querySelector('.review-checkbox');
        if (checkbox) {
            checkbox.addEventListener('change', updateBatchOperationsVisibility);
        }
        
        // 绑定展开/收起按钮
        toggleBtns.forEach(btn => {
            btn.addEventListener('click', (e) => toggleContentView(e.target));
        });

        // 应用差异高亮到建议更新内容
        const proposedShortDiv = updateElement.querySelector(`#proposed-${update.id}`);
        const proposedFullDiv = updateElement.querySelector(`#proposed-full-${update.id}`);

        if (proposedShortDiv && proposedFullDiv) {
            // 检查是否只是key_change更新
            const isKeyChangeOnly = update.proposed_content && update.proposed_content.length < 500;

            // 生成高亮的完整内容 - 使用formatNewlines处理换行
            const highlightedFullContent = highlightTextDifferences(
                update.original_content || '',
                update.proposed_content || '',
                isKeyChangeOnly  // 如果是短内容,认为是key_change
            );

            // 生成高亮的截断内容
            const truncatedProposed = truncateText(update.proposed_content || '', 200);
            const highlightedShortContent = highlightTextDifferences(
                update.original_content || '',
                truncatedProposed,
                isKeyChangeOnly
            );

            // 设置内容(使用innerHTML因为包含HTML标记)
            proposedShortDiv.innerHTML = highlightedShortContent;
            proposedFullDiv.innerHTML = highlightedFullContent;
        }

        // 同样处理原始内容的换行符显示
        const originalShortDiv = updateElement.querySelector(`#original-${update.id}`);
        const originalFullDiv = updateElement.querySelector(`#original-full-${update.id}`);

        if (originalShortDiv && originalFullDiv) {
            // 格式化原始内容的换行符
            originalShortDiv.innerHTML = formatNewlines(truncateText(update.original_content || '', 200));
            originalFullDiv.innerHTML = formatNewlines(update.original_content || '');
        }

        reviewList.appendChild(updateElement);
    });
}

// 切换内容显示（展开/收起）
function toggleContentView(button) {
    const target = button.getAttribute('data-target');
    const shortContent = document.getElementById(target);
    
    // 更智能的全内容ID生成
    let fullContentId;
    if (target.includes('reviewed-original-')) {
        fullContentId = target.replace('reviewed-original-', 'reviewed-original-full-');
    } else if (target.includes('reviewed-proposed-')) {
        fullContentId = target.replace('reviewed-proposed-', 'reviewed-proposed-full-');
    } else if (target.includes('original-')) {
        fullContentId = target.replace('original-', 'original-full-');
    } else if (target.includes('proposed-')) {
        fullContentId = target.replace('proposed-', 'proposed-full-');
    } else {
        fullContentId = target + '-full';
    }
    
    const fullContent = document.getElementById(fullContentId);
    
    if (!shortContent || !fullContent) {
        console.warn('找不到内容元素:', target, fullContentId);
        return;
    }
    
    const isCollapsed = shortContent.getAttribute('data-collapsed') === 'true';
    
    if (isCollapsed) {
        // 展开
        shortContent.style.display = 'none';
        fullContent.style.display = 'block';
        button.textContent = '收起内容';
        shortContent.setAttribute('data-collapsed', 'false');
        fullContent.setAttribute('data-collapsed', 'false');
    } else {
        // 收起
        shortContent.style.display = 'block';
        fullContent.style.display = 'none';
        button.textContent = '展开完整内容';
        shortContent.setAttribute('data-collapsed', 'true');
        fullContent.setAttribute('data-collapsed', 'true');
    }
}

// 更新审查统计
async function updateReviewStats(pendingUpdates = []) {
    try {
        // 获取已审查的数据来计算统计
        const reviewedResponse = await fetch('/api/persona_updates/reviewed');
        let reviewedUpdates = [];
        
        if (reviewedResponse.ok) {
            const reviewedData = await reviewedResponse.json();
            if (reviewedData && reviewedData.success && Array.isArray(reviewedData.updates)) {
                reviewedUpdates = reviewedData.updates;
            }
        }
        
        // 计算统计数据
        const pending = pendingUpdates.length;
        const approved = reviewedUpdates.filter(u => u.status === 'approved').length;
        const rejected = reviewedUpdates.filter(u => u.status === 'rejected').length;
        
        // 更新页面显示
        const pendingElement = document.getElementById('pending-reviews');
        const approvedElement = document.getElementById('approved-reviews');  
        const rejectedElement = document.getElementById('rejected-reviews');
        
        if (pendingElement) pendingElement.textContent = pending;
        if (approvedElement) approvedElement.textContent = approved;
        if (rejectedElement) rejectedElement.textContent = rejected;
        
    } catch (error) {
        console.error('更新审查统计失败:', error);
        // 出错时至少显示待审查数量
        const pending = pendingUpdates.length;
        const pendingElement = document.getElementById('pending-reviews');
        if (pendingElement) pendingElement.textContent = pending;
    }
}

// 渲染学习状态
function renderLearningStatus(status) {
    const session = status.current_session;
    if (session) {
        document.getElementById('current-session-id').textContent = session.session_id;
        document.getElementById('session-start-time').textContent = session.start_time;
        document.getElementById('session-messages').textContent = session.messages_processed;
        
        const statusBadge = document.getElementById('session-status');
        statusBadge.textContent = session.status === 'active' ? '运行中' : '已停止';
        statusBadge.className = `status-badge ${session.status === 'active' ? 'active' : ''}`;
    }
}

// 保存配置
async function saveConfiguration() {
    // 收集所有配置项
    const newConfig = {
        // 基础开关
        enable_message_capture: document.getElementById('enableMessageCapture')?.checked || false,
        enable_auto_learning: document.getElementById('enableAutoLearning')?.checked || false,
        enable_realtime_learning: document.getElementById('enableRealtimeLearning')?.checked || false,
        enable_realtime_llm_filter: document.getElementById('enableRealtimeLLMFilter')?.checked || false,
        enable_web_interface: document.getElementById('enableWebInterface')?.checked || true,
        web_interface_port: parseInt(document.getElementById('webInterfacePort')?.value) || 7833,
        
        // MaiBot增强功能
        enable_maibot_features: document.getElementById('enableMaibotFeatures')?.checked || true,
        enable_expression_patterns: document.getElementById('enableExpressionPatterns')?.checked || true,
        enable_memory_graph: document.getElementById('enableMemoryGraph')?.checked || true,
        enable_knowledge_graph: document.getElementById('enableKnowledgeGraph')?.checked || true,
        enable_time_decay: document.getElementById('enableTimeDecay')?.checked || true,
        
        // QQ号设置
        target_qq_list: (document.getElementById('targetQQList')?.value || '').split(',').map(qq => qq.trim()).filter(qq => qq),
        target_blacklist: (document.getElementById('targetBlacklist')?.value || '').split(',').map(qq => qq.trim()).filter(qq => qq),
        
        // LLM提供商设置
        filter_provider_id: document.getElementById('filterProviderId')?.value || null,
        refine_provider_id: document.getElementById('refineProviderId')?.value || null,
        reinforce_provider_id: document.getElementById('reinforceProviderId')?.value || null,
        
        // 学习参数
        learning_interval_hours: parseInt(document.getElementById('learningInterval')?.value) || 6,
        min_messages_for_learning: parseInt(document.getElementById('minMessagesForLearning')?.value) || 50,
        max_messages_per_batch: parseInt(document.getElementById('maxMessagesPerBatch')?.value) || 200,
        
        // 筛选参数
        message_min_length: parseInt(document.getElementById('messageMinLength')?.value) || 5,
        message_max_length: parseInt(document.getElementById('messageMaxLength')?.value) || 500,
        confidence_threshold: parseFloat(document.getElementById('confidenceThreshold')?.value) || 0.7,
        relevance_threshold: parseFloat(document.getElementById('relevanceThreshold')?.value) || 0.6,
        
        // 风格分析参数
        style_analysis_batch_size: parseInt(document.getElementById('styleAnalysisBatchSize')?.value) || 100,
        style_update_threshold: parseFloat(document.getElementById('styleUpdateThreshold')?.value) || 0.6,
        
        // 机器学习设置
        enable_ml_analysis: document.getElementById('enableMLAnalysis')?.checked || true,
        max_ml_sample_size: parseInt(document.getElementById('maxMLSampleSize')?.value) || 100,
        ml_cache_timeout_hours: parseInt(document.getElementById('mlCacheTimeoutHours')?.value) || 1,
        
        // 人格备份设置
        auto_backup_enabled: document.getElementById('autoBackupEnabled')?.checked || true,
        backup_interval_hours: parseInt(document.getElementById('backupIntervalHours')?.value) || 24,
        max_backups_per_group: parseInt(document.getElementById('maxBackupsPerGroup')?.value) || 10,
        
        // 高级设置
        debug_mode: document.getElementById('debugMode')?.checked || false,
        save_raw_messages: document.getElementById('saveRawMessages')?.checked || true,
        auto_backup_interval_days: parseInt(document.getElementById('autoBackupIntervalDays')?.value) || 7,
        
        // 好感度系统配置
        enable_affection_system: document.getElementById('enableAffectionSystem')?.checked || true,
        max_total_affection: parseInt(document.getElementById('maxTotalAffection')?.value) || 250,
        max_user_affection: parseInt(document.getElementById('maxUserAffection')?.value) || 100,
        affection_decay_rate: parseFloat(document.getElementById('affectionDecayRate')?.value) || 0.95,
        daily_mood_change: document.getElementById('dailyMoodChange')?.checked || true,
        mood_affect_affection: document.getElementById('moodAffectAffection')?.checked || true,
        
        // 情绪系统配置
        enable_daily_mood: document.getElementById('enableDailyMood')?.checked || true,
        enable_startup_random_mood: document.getElementById('enableStartupRandomMood')?.checked || true,
        mood_change_hour: parseInt(document.getElementById('moodChangeHour')?.value) || 6,
        mood_persistence_hours: parseInt(document.getElementById('moodPersistenceHours')?.value) || 24,
        
        // PersonaUpdater配置
        persona_merge_strategy: document.getElementById('personaMergeStrategy')?.value || 'smart',
        max_mood_imitation_dialogs: parseInt(document.getElementById('maxMoodImitationDialogs')?.value) || 20,
        enable_persona_evolution: document.getElementById('enablePersonaEvolution')?.checked || true,
        persona_compatibility_threshold: parseFloat(document.getElementById('personaCompatibilityThreshold')?.value) || 0.6,
        
        // 人格更新方式配置
        auto_apply_persona_updates: document.getElementById('autoApplyPersonaUpdates')?.checked || true,
        persona_update_backup_enabled: document.getElementById('personaUpdateBackupEnabled')?.checked || true
    };
    
    try {
        showSpinner(document.getElementById('saveConfig'));
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(newConfig)
        });
        
        if (response.ok) {
            const result = await response.json();
            currentConfig = result.new_config;
            showSuccess('配置保存成功，所有设置已同步更新');
            
            // 实时更新显示
            setTimeout(() => {
                // 重新加载配置以确保同步
                loadConfig();
                // 更新仪表盘数据
                renderOverviewStats();
                updateSystemStatusRadar();
                // 刷新图表数据
                if (document.querySelector('#dashboard-page.active')) {
                    refreshDashboard();
                }
            }, 1000);
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '保存配置失败');
        }
    } catch (error) {
        console.error('保存配置失败:', error);
        showError(`保存配置失败: ${error.message}`);
    } finally {
        hideSpinner(document.getElementById('saveConfig'));
    }
}

// 重置配置
async function resetConfiguration() {
    if (confirm('确定要重置配置到默认值吗？')) {
        try {
            // 重置表单到默认值
            document.getElementById('enableMessageCapture').checked = true;
            document.getElementById('enableAutoLearning').checked = true;
            document.getElementById('enableRealtimeLearning').checked = false;
            document.getElementById('targetQQList').value = '';
            document.getElementById('learningInterval').value = 6;
            document.getElementById('filterModel').value = 'gpt-4o-mini';
            document.getElementById('refineModel').value = 'gpt-4o';
            
            showSuccess('配置已重置到默认值');
        } catch (error) {
            showError('重置配置失败');
        }
    }
}

// 审查人格更新
async function reviewUpdate(updateId, action) {
    try {
        const response = await fetch(`/api/persona_updates/${updateId}/review`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action })
        });
        
        if (response.ok) {
            showSuccess(`人格更新已${action === 'approve' ? '批准' : '拒绝'}`);
            await loadPersonaUpdates(); // 重新加载列表
        } else {
            throw new Error('审查操作失败');
        }
    } catch (error) {
        console.error('审查操作失败:', error);
        showError('操作失败，请重试');
    }
}

// 编辑人格更新内容
function editPersonaUpdate(updateId) {
    // 查找待审查的人格更新数据
    fetch(`/api/persona_updates`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                showError('获取更新列表失败');
                return;
            }
            
            const update = data.updates.find(u => u.id === updateId);
            if (!update) {
                showError('未找到对应的更新记录');
                return;
            }
            
            showPersonaEditDialog(update);
        })
        .catch(error => {
            console.error('获取更新详情失败:', error);
            showError('获取更新详情失败');
        });
}

// 显示人格编辑对话框
function showPersonaEditDialog(update) {
    const dialogHTML = `
        <div class="persona-edit-overlay" id="personaEditOverlay">
            <div class="persona-edit-dialog">
                <div class="dialog-header">
                    <h3>编辑人格更新 - ID: ${update.id}</h3>
                    <button class="close-btn" id="closeEditDialogBtn">
                        <i class="material-icons">close</i>
                    </button>
                </div>
                <div class="dialog-content">
                    <div class="update-info">
                        <p><strong>更新类型:</strong> ${update.update_type || '人格更新'}</p>
                        <p><strong>置信度:</strong> ${(update.confidence_score * 100).toFixed(1)}%</p>
                        <p><strong>原因:</strong> ${update.reason || '未提供'}</p>
                        <p><strong>时间:</strong> ${new Date(update.timestamp * 1000).toLocaleString()}</p>
                        ${update.total_raw_messages ? `<p><strong>样本总数:</strong> ${update.total_raw_messages} 条原始消息</p>` : ''}
                        ${update.messages_analyzed ? `<p><strong>分析样本:</strong> ${update.messages_analyzed} 条筛选消息</p>` : ''}
                    </div>

                    ${update.features_content ? `
                    <div class="content-editor">
                        <div class="editor-section">
                            <h4><i class="material-icons">analytics</i> 提炼的风格特征</h4>
                            <textarea id="featuresContent" readonly rows="8" style="resize: vertical; min-height: 150px; background-color: #f5f7fa; font-family: 'Courier New', monospace;">${update.features_content}</textarea>
                        </div>
                    </div>
                    ` : ''}

                    <div class="content-editor">
                        <div class="editor-section">
                            <h4>原始人格内容</h4>
                            <textarea id="originalContent" readonly rows="15" style="resize: vertical; min-height: 200px;">${update.original_content || ''}</textarea>
                        </div>

                        <div class="editor-section">
                            <h4>建议更新内容</h4>
                            <textarea id="proposedContent" rows="15" style="resize: vertical; min-height: 200px;">${update.proposed_content || ''}</textarea>
                            <small class="form-hint">💡 您可以手动修改建议的人格内容，然后选择批准或拒绝</small>
                        </div>
                        
                        <div class="editor-section">
                            <h4>审查备注</h4>
                            <textarea id="reviewComment" rows="3" placeholder="可选：添加审查备注..."></textarea>
                        </div>
                    </div>
                </div>
                <div class="dialog-actions">
                    <button class="btn btn-secondary" id="cancelEditBtn">
                        <i class="material-icons">close</i>
                        取消
                    </button>
                    <button class="btn btn-danger" id="rejectEditBtn">
                        <i class="material-icons">close</i>
                        拒绝更新
                    </button>
                    <button class="btn btn-success" id="approveEditBtn">
                        <i class="material-icons">check</i>
                        批准更新
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 添加对话框到页面
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
    
    // 绑定事件处理器
    const overlay = document.getElementById('personaEditOverlay');
    const closeBtn = document.getElementById('closeEditDialogBtn');
    const cancelBtn = document.getElementById('cancelEditBtn');
    const rejectBtn = document.getElementById('rejectEditBtn');
    const approveBtn = document.getElementById('approveEditBtn');
    
    // 关闭对话框事件
    const closeDialog = () => closePersonaEditDialog();
    
    closeBtn.addEventListener('click', closeDialog);
    cancelBtn.addEventListener('click', closeDialog);
    
    // 批准和拒绝事件
    rejectBtn.addEventListener('click', () => reviewPersonaUpdate(update.id, 'reject'));
    approveBtn.addEventListener('click', () => reviewPersonaUpdate(update.id, 'approve'));
    
    // 添加点击外部关闭功能
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closePersonaEditDialog();
        }
    });
}

// 关闭人格编辑对话框
function closePersonaEditDialog() {
    const overlay = document.getElementById('personaEditOverlay');
    if (overlay) {
        overlay.remove();
    }
}

// 通过编辑对话框审查人格更新
async function reviewPersonaUpdate(updateId, action) {
    try {
        const proposedContent = document.getElementById('proposedContent')?.value || '';
        const reviewComment = document.getElementById('reviewComment')?.value || '';
        
        const response = await fetch(`/api/persona_updates/${updateId}/review`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                action,
                comment: reviewComment,
                modified_content: proposedContent
            })
        });
        
        if (response.ok) {
            showSuccess(`人格更新已${action === 'approve' ? '批准' : '拒绝'}`);
            closePersonaEditDialog();
            await loadPersonaUpdates(); // 重新加载列表
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '审查操作失败');
        }
    } catch (error) {
        console.error('审查操作失败:', error);
        showError(`操作失败: ${error.message}`);
    }
}

// 删除人格更新记录
async function deletePersonaUpdate(updateId) {
    if (!confirm('确定要删除这条记录吗？此操作不可撤销。')) {
        return;
    }

    try {
        // 保留完整ID（包含前缀如 style_、persona_learning_），后端根据前缀区分类型
        const response = await fetch(`/api/persona_updates/${encodeURIComponent(updateId)}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            showSuccess(data.message);
            // 重新加载列表
            await loadPendingReviews();
            // 如果当前在审查历史页面，也刷新已审查列表
            if (document.querySelector('#reviewed-tab.active')) {
                loadReviewedPersonaUpdates();
            }
        } else {
            showError(data.error || '删除失败');
        }
    } catch (error) {
        console.error('删除操作失败:', error);
        showError('删除操作失败');
    }
}

// 批量删除人格更新记录
async function batchDeletePersonaUpdates(updateIds) {
    if (!updateIds || updateIds.length === 0) {
        showError('请选择要删除的记录');
        return;
    }

    if (!confirm(`确定要删除选中的 ${updateIds.length} 条记录吗？此操作不可撤销。`)) {
        return;
    }

    try {
        // 保留完整ID（包含前缀如 style_、persona_learning_），后端根据前缀区分类型
        const response = await fetch('/api/persona_updates/batch_delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ update_ids: updateIds })
        });

        const data = await response.json();

        if (data.success) {
            showSuccess(data.message);
            // 重新加载列表
            await loadPendingReviews();
            // 如果当前在审查历史页面，也刷新已审查列表
            if (document.querySelector('#reviewed-tab.active')) {
                loadReviewedPersonaUpdates();
            }
            // 清除选中状态
            clearAllSelections();
        } else {
            showError(data.error || '批量删除失败');
        }
    } catch (error) {
        console.error('批量删除操作失败:', error);
        showError('批量删除操作失败');
    }
}

// 批量审查人格更新记录
async function batchReviewPersonaUpdates(updateIds, action, comment = '') {
    if (!updateIds || updateIds.length === 0) {
        showError('请选择要操作的记录');
        return;
    }

    const actionText = action === 'approve' ? '批准' : '拒绝';
    if (!confirm(`确定要批量${actionText}选中的 ${updateIds.length} 条记录吗？`)) {
        return;
    }

    try {
        // 保留完整ID（包含前缀如 style_、persona_learning_），后端根据前缀区分类型
        const response = await fetch('/api/persona_updates/batch_review', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                update_ids: updateIds,
                action: action,
                comment: comment
            })
        });

        const data = await response.json();
        
        if (data.success) {
            showSuccess(data.message);
            // 重新加载列表
            await loadPendingReviews();
            // 如果当前在审查历史页面，也刷新已审查列表
            if (document.querySelector('#reviewed-tab.active')) {
                loadReviewedPersonaUpdates();
            }
            // 清除选中状态
            clearAllSelections();
        } else {
            showError(data.error || `批量${actionText}失败`);
        }
    } catch (error) {
        console.error(`批量${actionText}操作失败:`, error);
        showError(`批量${actionText}操作失败`);
    }
}

// 获取选中的记录ID列表
function getSelectedReviewIds() {
    const checkboxes = document.querySelectorAll('.review-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function getSelectedReviewedIds() {
    const checkboxes = document.querySelectorAll('.reviewed-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// 清除所有选中状态
function clearAllSelections() {
    document.querySelectorAll('.review-checkbox, .reviewed-checkbox').forEach(cb => {
        cb.checked = false;
    });
    updateBatchOperationsVisibility();
}

// 更新批量操作按钮可见性
function updateBatchOperationsVisibility() {
    const selectedPendingCount = getSelectedReviewIds().length;
    const selectedReviewedCount = getSelectedReviewedIds().length;
    
    // 更新待审查页面的批量操作按钮
    const pendingBatchOps = document.getElementById('pending-batch-operations');
    if (pendingBatchOps) {
        pendingBatchOps.style.display = selectedPendingCount > 0 ? 'block' : 'none';
    }
    
    // 更新审查历史页面的批量操作按钮
    const reviewedBatchOps = document.getElementById('reviewed-batch-operations');
    if (reviewedBatchOps) {
        reviewedBatchOps.style.display = selectedReviewedCount > 0 ? 'block' : 'none';
    }
    
    // 更新选中计数显示
    const pendingSelectedCount = document.getElementById('pending-selected-count');
    if (pendingSelectedCount) {
        pendingSelectedCount.textContent = selectedPendingCount;
    }
    
    const reviewedSelectedCount = document.getElementById('reviewed-selected-count');
    if (reviewedSelectedCount) {
        reviewedSelectedCount.textContent = selectedReviewedCount;
    }
}

// 全选/取消全选
function toggleSelectAllPending() {
    const selectAllCheckbox = document.getElementById('select-all-pending');
    const reviewCheckboxes = document.querySelectorAll('.review-checkbox');
    
    reviewCheckboxes.forEach(cb => {
        cb.checked = selectAllCheckbox.checked;
    });
    
    updateBatchOperationsVisibility();
}

function toggleSelectAllReviewed() {
    const selectAllCheckbox = document.getElementById('select-all-reviewed');
    const reviewCheckboxes = document.querySelectorAll('.reviewed-checkbox');
    
    reviewCheckboxes.forEach(cb => {
        cb.checked = selectAllCheckbox.checked;
    });
    
    updateBatchOperationsVisibility();
}

// 更新LLM使用图表
function updateLLMUsageChart(timeRange) {
    // 模拟根据时间范围更新数据
    console.log('更新LLM使用图表:', timeRange);
    if (chartInstances['llm-usage-pie']) {
        // 这里可以重新获取数据并更新图表
        initializeLLMUsagePie();
    }
}

// 更新消息趋势图表
function updateMessageTrendChart(timeRange) {
    console.log('更新消息趋势图表:', timeRange);
    if (chartInstances['message-trend-line']) {
        initializeMessageTrendLine();
    }
}

// 更新活跃度热力图
function updateActivityHeatmap(period) {
    console.log('更新活跃度热力图:', period);
    if (chartInstances['activity-heatmap']) {
        initializeActivityHeatmap();
    }
}

// 更新系统状态雷达图
function updateSystemStatusRadar() {
    if (chartInstances['system-status-radar']) {
        // 根据当前配置更新状态值
        const values = [
            currentConfig.enable_message_capture ? 95 : 0,
            85, 78, 88, 82, 95
        ];
        
        const option = chartInstances['system-status-radar'].getOption();
        option.series[0].data[0].value = values;
        chartInstances['system-status-radar'].setOption(option);
    }
}

// 加载页面数据
async function loadPageData(page) {
    // 当离开人格管理页面时，停止自动更新
    if (page !== 'persona-management') {
        stopPersonaAutoUpdate();
    }
    
    switch (page) {
        case 'dashboard':
            await loadMetrics();
            renderOverviewStats();
            // 更新所有图表
            Object.values(chartInstances).forEach(chart => {
                if (chart && typeof chart.resize === 'function') {
                    setTimeout(() => chart.resize(), 100);
                }
            });
            break;
        case 'config':
            await loadConfig();
            break;
        case 'persona-review':
            await loadPersonaUpdates();
            break;
        case 'learning-status':
            await loadLearningStatus();
            break;
        case 'style-learning':
            await loadStyleLearningData();
            break;
        case 'persona-management':
            await loadPersonaManagementData();
            break;
        case 'metrics':
            await loadMetrics();
            renderDetailedMetrics();
            break;
        case 'social-relations':
            await loadGroupList();
            startSocialRelationsAutoRefresh(); // 启动自动刷新
            break;
        case 'jargon-learning':
            await refreshJargonPage();
            break;
        default:
            stopSocialRelationsAutoRefresh(); // 离开社交关系页面时停止刷新
            break;
    }
}

// 加载对话风格学习数据
async function loadStyleLearningData() {
    updateRefreshIndicator('加载中...');
    try {
        // 并行加载学习成果和模式数据
        const [resultsResponse, patternsResponse] = await Promise.all([
            fetch('/api/style_learning/results'),
            fetch('/api/style_learning/patterns')
        ]);
        
        if (resultsResponse.ok && patternsResponse.ok) {
            const results = await resultsResponse.json();
            const patterns = await patternsResponse.json();
            
            // 检查是否有错误
            if (results.error) {
                throw new Error(results.error);
            }
            if (patterns.error) {
                throw new Error(patterns.error);
            }
            
            // 更新统计概览
            renderStyleLearningStats(results.statistics || {});
            
            // 初始化图表
            initializeStyleLearningCharts(results, patterns);
            
            // 更新学习模式列表
            renderLearningPatterns(patterns);
            
            updateRefreshIndicator('刚刚更新');
        } else {
            const resultsText = await resultsResponse.text();
            const patternsText = await patternsResponse.text();
            console.error('API响应错误:', { resultsText, patternsText });
            throw new Error('获取风格学习数据失败');
        }
    } catch (error) {
        console.error('加载对话风格学习数据失败:', error);
        showError(`加载数据失败: ${error.message || '请检查网络连接'}`);
        updateRefreshIndicator('更新失败');
    }
}

// 渲染风格学习统计
function renderStyleLearningStats(stats) {
    document.getElementById('style-types-count').textContent = stats.unique_styles || 0;
    document.getElementById('avg-confidence').textContent = (stats.avg_confidence || 0) + '%';
    document.getElementById('total-samples').textContent = formatNumber(stats.total_samples || 0);
    
    // 格式化最新更新时间
    if (stats.latest_update && !isNaN(stats.latest_update)) {
        const updateTime = new Date(stats.latest_update * 1000);
        if (isNaN(updateTime.getTime())) {
            document.getElementById('latest-update').textContent = '--';
        } else {
            document.getElementById('latest-update').textContent = updateTime.toLocaleString();
        }
    } else {
        document.getElementById('latest-update').textContent = '--';
    }
}

// 初始化风格学习图表
function initializeStyleLearningCharts(results, patterns) {
    // 风格学习进度图
    initializeStyleProgressChart(results.style_progress || []);
    
    // 情感表达模式图
    initializeEmotionPatternsChart(patterns.emotion_patterns || []);
    
    // 语言风格分布图
    initializeLanguageStyleChart(patterns.language_patterns || []);
    
    // 主题偏好分析图
    initializeTopicPreferencesChart(patterns.topic_preferences || []);
}

// 风格学习进度图表
function initializeStyleProgressChart(progressData) {
    const chartDom = document.getElementById('style-progress-chart');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['style-progress-chart'] = chart;
    
    // 检查数据有效性并提供默认值
    if (!progressData || !Array.isArray(progressData) || progressData.length === 0) {
        // 显示空数据图表
        const option = {
            title: {
                text: '暂无风格学习数据',
                left: 'center',
                top: 'middle',
                textStyle: {
                    fontSize: 14,
                    color: '#999'
                }
            },
            xAxis: { type: 'category', data: [] },
            yAxis: [{ type: 'value', name: '置信度(%)' }, { type: 'value', name: '样本数量' }],
            series: [{ name: '置信度', type: 'bar', data: [] }, { name: '样本数量', type: 'line', data: [] }]
        };
        chart.setOption(option);
        return;
    }
    
    const styles = progressData.map(item => {
        // 使用 group_id 或者时间戳作为标签
        if (item.group_id) {
            return `群组${item.group_id}`;
        } else if (item.timestamp) {
            const date = new Date(item.timestamp * 1000);
            return date.toLocaleDateString();
        }
        return '未知';
    });
    const confidenceData = progressData.map(item => {
        // quality_score 通常是 0-1 之间的值，转换为百分比
        return (item.quality_score || 0) * 100;
    });
    const sampleData = progressData.map(item => {
        // 使用 filtered_count 或 message_count 作为样本数量
        return item.filtered_count || item.message_count || item.total_samples || 0;
    });
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            }
        },
        legend: {
            data: ['置信度', '样本数量']
        },
        xAxis: {
            type: 'category',
            data: styles,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: [
            {
                type: 'value',
                name: '置信度(%)',
                position: 'left',
                max: 100
            },
            {
                type: 'value',
                name: '样本数量',
                position: 'right'
            }
        ],
        series: [
            {
                name: '置信度',
                type: 'bar',
                data: confidenceData,
                itemStyle: {
                    color: '#1976d2'
                }
            },
            {
                name: '样本数量',
                type: 'line',
                yAxisIndex: 1,
                data: sampleData,
                itemStyle: {
                    color: '#4caf50'
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 情感表达模式图表
function initializeEmotionPatternsChart(emotionData) {
    const chartDom = document.getElementById('emotion-patterns-chart');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['emotion-patterns-chart'] = chart;
    
    // 检查数据有效性并提供默认值
    if (!emotionData || !Array.isArray(emotionData) || emotionData.length === 0) {
        // 显示空数据图表
        const option = {
            title: {
                text: '暂无情感模式数据',
                left: 'center',
                top: 'middle',
                textStyle: {
                    fontSize: 14,
                    color: '#999'
                }
            },
            series: [{
                name: '情感表达',
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '45%'],
                data: [{ name: '暂无数据', value: 1 }]
            }]
        };
        chart.setOption(option);
        return;
    }
    
    const data = emotionData.map(item => ({
        name: item.pattern || '未知模式',
        value: item.frequency || 0
    }));
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{a} <br/>{b}: {c} ({d}%)'
        },
        legend: {
            bottom: '5%',
            left: 'center'
        },
        series: [
            {
                name: '情感表达',
                type: 'pie',
                radius: ['40%', '70%'],
                center: ['50%', '45%'],
                data: data,
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 语言风格分布图表
function initializeLanguageStyleChart(languageData) {
    const chartDom = document.getElementById('language-style-chart');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['language-style-chart'] = chart;
    
    // 检查数据有效性并提供默认值
    if (!languageData || !Array.isArray(languageData) || languageData.length === 0) {
        // 显示空数据图表
        const option = {
            title: {
                text: '暂无语言风格数据',
                left: 'center',
                top: 'middle',
                textStyle: {
                    fontSize: 14,
                    color: '#999'
                }
            },
            xAxis: { type: 'category', data: ['暂无数据'] },
            yAxis: { type: 'value', name: '使用频率' },
            series: [{ name: '语言风格', type: 'bar', data: [0] }]
        };
        chart.setOption(option);
        return;
    }
    
    const styles = languageData.map(item => item.style || '未知风格');
    const frequencies = languageData.map(item => item.frequency || 0);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow'
            }
        },
        xAxis: {
            type: 'category',
            data: styles,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: {
            type: 'value',
            name: '使用频率'
        },
        series: [
            {
                name: '语言风格',
                type: 'bar',
                data: frequencies,
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#ff9800' },
                        { offset: 1, color: '#ffcc80' }
                    ])
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 主题偏好分析图表
function initializeTopicPreferencesChart(topicData) {
    const chartDom = document.getElementById('topic-preferences-chart');
    const chart = echarts.init(chartDom, 'material');
    chartInstances['topic-preferences-chart'] = chart;
    
    // 检查数据有效性并提供默认值
    if (!topicData || !Array.isArray(topicData) || topicData.length === 0) {
        // 显示空数据图表
        const option = {
            title: {
                text: '暂无主题偏好数据',
                left: 'center',
                top: 'middle',
                textStyle: {
                    fontSize: 14,
                    color: '#999'
                }
            },
            radar: {
                indicator: [{ name: '暂无数据', max: 100 }],
                center: ['50%', '50%'],
                radius: '75%'
            },
            series: [{
                name: '主题偏好',
                type: 'radar',
                data: [{ value: [0], name: '兴趣水平' }]
            }]
        };
        chart.setOption(option);
        return;
    }
    
    const topics = topicData.map(item => item.topic || '未知主题');
    const interestLevels = topicData.map(item => item.interest_level || 0);
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c}%'
        },
        radar: {
            indicator: topics.map(topic => ({ name: topic, max: 100 })),
            center: ['50%', '50%'],
            radius: '75%'
        },
        series: [
            {
                name: '主题偏好',
                type: 'radar',
                data: [
                    {
                        value: interestLevels,
                        name: '兴趣水平',
                        itemStyle: { color: '#9c27b0' },
                        areaStyle: { opacity: 0.3 }
                    }
                ]
            }
        ]
    };
    
    chart.setOption(option);
}

// 渲染学习模式列表
function renderLearningPatterns(patterns) {
    // 检查patterns数据有效性
    if (!patterns || typeof patterns !== 'object') {
        patterns = {
            emotion_patterns: [],
            language_patterns: [],
            topic_preferences: []
        };
    }
    
    // 渲染情感表达模式
    const emotionList = document.getElementById('emotion-patterns-list');
    const emotionPatterns = patterns.emotion_patterns || [];
    if (emotionPatterns.length === 0) {
        emotionList.innerHTML = '<div class="no-data">暂无情感表达模式数据</div>';
    } else {
        emotionList.innerHTML = emotionPatterns.map(pattern => `
            <div class="pattern-item">
                <span class="pattern-name">${pattern.pattern || '未知模式'}</span>
                <span class="pattern-frequency">频率: ${pattern.frequency || 0}</span>
                <span class="pattern-confidence">置信度: ${pattern.confidence || 0}%</span>
            </div>
        `).join('');
    }
    
    // 渲染语言风格模式
    const languageList = document.getElementById('language-patterns-list');
    const languagePatterns = patterns.language_patterns || [];
    if (languagePatterns.length === 0) {
        languageList.innerHTML = '<div class="no-data">暂无语言风格模式数据</div>';
    } else {
        languageList.innerHTML = languagePatterns.map(pattern => `
            <div class="pattern-item">
                <span class="pattern-name">${pattern.style || '未知风格'}</span>
                <span class="pattern-context">环境: ${pattern.context || 'general'}</span>
                <span class="pattern-frequency">频率: ${pattern.frequency || 0}</span>
            </div>
        `).join('');
    }
    
    // 渲染主题偏好模式
    const topicList = document.getElementById('topic-patterns-list');
    const topicPatterns = patterns.topic_preferences || [];
    if (topicPatterns.length === 0) {
        topicList.innerHTML = '<div class="no-data">暂无主题偏好模式数据</div>';
    } else {
        topicList.innerHTML = topicPatterns.map(pattern => `
            <div class="pattern-item">
                <span class="pattern-name">${pattern.topic || '未知主题'}</span>
                <span class="pattern-style">风格: ${pattern.response_style || 'normal'}</span>
                <span class="pattern-interest">兴趣度: ${pattern.interest_level || 0}%</span>
            </div>
        `).join('');
    }
}

// 渲染详细监控
function renderDetailedMetrics() {
    // 加载详细监控数据
    fetch('/api/metrics/detailed')
        .then(response => response.json())
        .then(data => {
            // 使用真实数据初始化图表
            initializeAPIMetricsChart(data.api_metrics);
            initializeDBMetricsChart(data.database_metrics);
            initializeMemoryMetricsChart(data.system_metrics);
        })
        .catch(error => {
            console.error('加载详细监控数据失败:', error);
            // 使用空数据初始化图表
            initializeAPIMetricsChart({});
            initializeDBMetricsChart({});
            initializeMemoryMetricsChart({});
        });
}

// API监控图表
function initializeAPIMetricsChart(apiData = {}) {
    const chartDom = document.getElementById('api-metrics-chart');
    if (!chartDom) return;
    
    const chart = echarts.init(chartDom, 'material');
    chartInstances['api-metrics-chart'] = chart;
    
    const hours = apiData.hours || ['暂无数据'];
    const responseTimes = apiData.response_times || [0];
    
    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: '{b}<br/>{a}: {c}ms'
        },
        xAxis: {
            type: 'category',
            data: hours
        },
        yAxis: {
            type: 'value',
            name: '响应时间(ms)'
        },
        series: [
            {
                name: 'API响应时间',
                type: 'line',
                data: responseTimes,
                smooth: true,
                itemStyle: { color: '#1976d2' },
                areaStyle: { opacity: 0.3 }
            }
        ]
    };
    
    chart.setOption(option);
}

// 数据库监控图表
function initializeDBMetricsChart(dbData = {}) {
    const chartDom = document.getElementById('db-metrics-chart');
    if (!chartDom) return;
    
    const chart = echarts.init(chartDom, 'material');
    chartInstances['db-metrics-chart'] = chart;
    
    const tableStats = dbData.table_stats || {};
    const tableNames = Object.keys(tableStats);
    const tableCounts = Object.values(tableStats);
    
    // 如果没有数据，显示空图表
    const data = tableNames.length > 0 ? tableCounts : [0];
    const labels = tableNames.length > 0 ? tableNames : ['暂无数据'];
    
    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: '{b}<br/>{a}: {c} 条记录'
        },
        xAxis: {
            type: 'category',
            data: labels,
            axisLabel: {
                rotate: 45
            }
        },
        yAxis: {
            type: 'value',
            name: '记录数量'
        },
        series: [
            {
                name: '数据表记录',
                type: 'bar',
                data: data,
                itemStyle: { 
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: '#4caf50' },
                        { offset: 1, color: '#81c784' }
                    ])
                }
            }
        ]
    };
    
    chart.setOption(option);
}

// 内存使用图表
function initializeMemoryMetricsChart(systemData = {}) {
    const chartDom = document.getElementById('memory-metrics-chart');
    if (!chartDom) return;
    
    const chart = echarts.init(chartDom, 'material');
    chartInstances['memory-metrics-chart'] = chart;
    
    const memoryPercent = systemData.memory_percent || 0;
    const cpuPercent = systemData.cpu_percent || 0;
    const diskPercent = systemData.disk_percent || 0;
    
    // 显示实时系统资源使用情况
    const option = {
        tooltip: {
            formatter: '{a}<br/>{b}: {c}%'
        },
        radar: {
            indicator: [
                { name: 'CPU', max: 100 },
                { name: '内存', max: 100 },
                { name: '磁盘', max: 100 }
            ],
            center: ['50%', '50%'],
            radius: '75%'
        },
        series: [
            {
                name: '系统资源',
                type: 'radar',
                data: [
                    {
                        value: [cpuPercent, memoryPercent, diskPercent],
                        name: '当前使用率',
                        itemStyle: { color: '#ff9800' },
                        areaStyle: { opacity: 0.3 }
                    }
                ]
            }
        ]
    };
    
    chart.setOption(option);
}

// 学习历史图表
function initializeLearningHistoryChart() {
    const chartDom = document.getElementById('learning-history-chart');
    if (!chartDom) return;
    
    const chart = echarts.init(chartDom, 'material');
    chartInstances['learning-history-chart'] = chart;
    
    // 从analytics/trends获取真实的学习历史数据
    fetch('/api/analytics/trends')
        .then(response => response.json())
        .then(data => {
            const dailyTrends = data.daily_trends || [];
            const dates = dailyTrends.map(item => item.date);
            const sessions = dailyTrends.map(item => item.learning_sessions || 0);
            
            const option = {
                tooltip: {
                    trigger: 'axis',
                    formatter: '{b}<br/>{a}: {c}次'
                },
                xAxis: {
                    type: 'category',
                    data: dates.length > 0 ? dates : ['暂无数据'],
                    axisLabel: {
                        rotate: 45
                    }
                },
                yAxis: {
                    type: 'value',
                    name: '学习次数'
                },
                series: [
                    {
                        name: '学习会话',
                        type: 'bar',
                        data: sessions.length > 0 ? sessions : [0],
                        itemStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                { offset: 0, color: '#9c27b0' },
                                { offset: 1, color: '#e1bee7' }
                            ])
                        }
                    }
                ]
            };
            
            chart.setOption(option);
        })
        .catch(error => {
            console.error('加载学习历史数据失败:', error);
            // 显示空图表
            const option = {
                tooltip: { trigger: 'axis' },
                xAxis: { type: 'category', data: ['暂无数据'] },
                yAxis: { type: 'value', name: '学习次数' },
                series: [{
                    name: '学习会话',
                    type: 'bar',
                    data: [0],
                    itemStyle: { color: '#9c27b0' }
                }]
            };
            chart.setOption(option);
        });
}

// 刷新仪表盘
async function refreshDashboard() {
    if (document.querySelector('#dashboard-page.active')) {
        updateRefreshIndicator('更新中...', true);
        
        try {
            await loadMetrics();
            renderOverviewStats();
            
            // 更新图表数据
            initializeLLMUsagePie();
            initializeMessageTrendLine();
            initializeResponseTimeBar();
            initializeLearningProgressGauge();
            
            updateRefreshIndicator('刚刚更新');
        } catch (error) {
            console.error('刷新失败:', error);
            updateRefreshIndicator('更新失败');
        }
    }
}

// 更新刷新指示器
function updateRefreshIndicator(text, spinning = false) {
    const indicator = document.getElementById('last-update');
    const icon = document.querySelector('.refresh-icon');
    
    if (indicator) indicator.textContent = text;
    if (icon) {
        if (spinning) {
            icon.classList.add('spinning');
        } else {
            icon.classList.remove('spinning');
        }
    }
}

// 工具函数
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function showSpinner(element) {
    const originalText = element.innerHTML;
    element.innerHTML = '<div class="loading"></div> 保存中...';
    element.disabled = true;
    element.dataset.originalText = originalText;
}

function hideSpinner(element) {
    element.innerHTML = element.dataset.originalText || element.innerHTML;
    element.disabled = false;
}

function showSuccess(message) {
    showNotification(message, 'success');
}

function showError(message) {
    showNotification(message, 'error');
}

function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        // 检查元素是否还在DOM中，避免removeChild错误
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 3000);
}

// 窗口大小改变时重新调整图表大小
window.addEventListener('resize', () => {
    Object.values(chartInstances).forEach(chart => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
});

// 页面可见性改变时暂停/恢复刷新
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        // 页面隐藏时暂停定时器
        console.log('页面隐藏，暂停刷新');
        stopPersonaAutoUpdate();
    } else {
        // 页面显示时可以立即刷新一次
        console.log('页面显示，恢复刷新');
        refreshDashboard();
        // 如果在人格管理页面，重启自动更新
        if (document.querySelector('#persona-management-page.active')) {
            startPersonaAutoUpdate();
        }
    }
});

// 页面卸载时清理定时器
window.addEventListener('beforeunload', () => {
    stopPersonaAutoUpdate();
});

// ========== 人格管理功能 ==========

let currentPersonas = [];
let defaultPersona = null;
let personaUpdateInterval = null;

// 启动人格数据实时更新
function startPersonaAutoUpdate() {
    // 清除之前的定时器
    if (personaUpdateInterval) {
        clearInterval(personaUpdateInterval);
    }
    
    // 每3秒更新一次人格数据
    personaUpdateInterval = setInterval(async () => {
        if (document.querySelector('#persona-management-page.active')) {
            await updatePersonaDataSilently();
        }
    }, 3000);
    
    console.log('人格数据自动更新已启动 (每3秒)');
}

// 停止人格数据实时更新
function stopPersonaAutoUpdate() {
    if (personaUpdateInterval) {
        clearInterval(personaUpdateInterval);
        personaUpdateInterval = null;
        console.log('人格数据自动更新已停止');
    }
}

// 静默更新人格数据（不显示加载提示）
async function updatePersonaDataSilently() {
    try {
        // 并行加载人格列表和默认人格
        const [personasResponse, defaultPersonaResponse] = await Promise.all([
            fetch('/api/persona_management/list'),
            fetch('/api/persona_management/default')
        ]);
        
        if (personasResponse.ok) {
            try {
                const personasData = await personasResponse.json();
                const newPersonas = personasData.personas || [];
                
                // 检查数据是否有变化
                if (JSON.stringify(newPersonas) !== JSON.stringify(currentPersonas)) {
                    currentPersonas = newPersonas;
                    renderPersonasGrid(currentPersonas);
                    console.log(`人格列表已更新 (${newPersonas.length} 个人格)`);
                }
            } catch (jsonError) {
                console.warn('静默更新: 解析人格列表JSON失败:', jsonError);
            }
        }
        
        if (defaultPersonaResponse.ok) {
            try {
                const newDefaultPersona = await defaultPersonaResponse.json();
                
                // 检查默认人格是否有变化
                if (JSON.stringify(newDefaultPersona) !== JSON.stringify(defaultPersona)) {
                    defaultPersona = newDefaultPersona;
                    renderDefaultPersona(defaultPersona);
                    console.log('默认人格已更新');
                }
            } catch (jsonError) {
                console.warn('静默更新: 解析默认人格JSON失败:', jsonError);
            }
        }
        
    } catch (error) {
        console.warn('静默更新人格数据失败:', error);
    }
}

// 加载人格管理数据
async function loadPersonaManagementData() {
    updateRefreshIndicator('加载中...');
    try {
        // 并行加载人格列表和默认人格
        const [personasResponse, defaultPersonaResponse] = await Promise.all([
            fetch('/api/persona_management/list'),
            fetch('/api/persona_management/default')
        ]);
        
        if (personasResponse.ok) {
            try {
                const personasData = await personasResponse.json();
                currentPersonas = personasData.personas || [];
                renderPersonasGrid(currentPersonas);
            } catch (jsonError) {
                console.error('解析人格列表JSON失败:', jsonError);
                currentPersonas = [];
                renderPersonasGrid([]);
            }
        } else {
            throw new Error('加载人格列表失败');
        }
        
        if (defaultPersonaResponse.ok) {
            try {
                defaultPersona = await defaultPersonaResponse.json();
                renderDefaultPersona(defaultPersona);
            } catch (jsonError) {
                console.error('解析默认人格JSON失败:', jsonError);
                renderDefaultPersona(null);
            }
        } else {
            console.warn('加载默认人格失败');
            renderDefaultPersona(null);
        }
        
        // 绑定事件处理器
        bindPersonaManagementEvents();
        
        // 启动自动更新
        startPersonaAutoUpdate();
        
        updateRefreshIndicator('刚刚更新');
    } catch (error) {
        console.error('加载人格管理数据失败:', error);
        showError(`加载数据失败: ${error.message}`);
        updateRefreshIndicator('更新失败');
        
        // 确保在错误情况下也有基本的UI
        renderPersonasGrid([]);
        renderDefaultPersona(null);
        
        // 即使出错也尝试启动自动更新
        startPersonaAutoUpdate();
    }
}

// 渲染人格列表
function renderPersonasGrid(personas) {
    const grid = document.getElementById('personas-grid');
    
    if (!personas || personas.length === 0) {
        grid.innerHTML = `
            <div class="no-personas">
                <i class="material-icons">person_outline</i>
                <h3>暂无人格</h3>
                <p>点击"创建人格"按钮来创建第一个人格</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = personas.map(persona => {
        // 安全地处理可能为null的数组和字符串
        if (!persona || typeof persona !== 'object') {
            return ''; // 跳过无效的persona对象
        }
        
        const personaId = (persona.persona_id && typeof persona.persona_id === 'string') ? persona.persona_id : 'unknown';
        const dialogsCount = (persona.begin_dialogs && Array.isArray(persona.begin_dialogs) && persona.begin_dialogs.length) ? persona.begin_dialogs.length : 0;
        const toolsCount = (persona.tools && Array.isArray(persona.tools) && persona.tools.length) ? persona.tools.length : 0;
        const systemPrompt = (persona.system_prompt && typeof persona.system_prompt === 'string') ? persona.system_prompt : '暂无系统提示';
        
        return `
        <div class="persona-card" data-persona-id="${personaId}">
            <div class="persona-card-header">
                <h3 class="persona-card-name" title="${personaId}">${personaId}</h3>
                <div class="persona-card-actions">
                    <button class="btn-icon" onclick="editPersona('${personaId}')" title="编辑">
                        <i class="material-icons">edit</i>
                    </button>
                    <button class="btn-icon" onclick="exportPersona('${personaId}')" title="导出">
                        <i class="material-icons">download</i>
                    </button>
                    <button class="btn-icon btn-danger" onclick="deletePersona('${personaId}')" title="删除">
                        <i class="material-icons">delete</i>
                    </button>
                </div>
            </div>
            <div class="persona-card-content">
                <div class="persona-field">
                    <label>系统提示:</label>
                    <div class="persona-prompt-preview">${truncateText(systemPrompt, 100)}</div>
                </div>
                <div class="persona-field">
                    <label>开始对话:</label>
                    <div class="persona-dialogs-preview">${dialogsCount} 条对话</div>
                </div>
                <div class="persona-field">
                    <label>工具:</label>
                    <div class="persona-tools-preview">${toolsCount} 个工具</div>
                </div>
                <div class="persona-field">
                    <label>创建时间:</label>
                    <div class="persona-time">${formatDateTime(persona.created_at)}</div>
                </div>
                <div class="persona-field">
                    <label>更新时间:</label>
                    <div class="persona-time">${formatDateTime(persona.updated_at)}</div>
                </div>
            </div>
        </div>
        `;
    }).join('');
}

// 渲染默认人格
function renderDefaultPersona(persona) {
    const card = document.getElementById('default-persona-card');
    
    if (!persona || typeof persona !== 'object') {
        card.innerHTML = `
            <div class="no-default-persona">
                <i class="material-icons">warning</i>
                <p>无法加载默认人格信息</p>
            </div>
        `;
        return;
    }
    
    // 安全地处理可能为null的数组和属性
    const dialogsCount = (persona.begin_dialogs && Array.isArray(persona.begin_dialogs) && persona.begin_dialogs.length) ? persona.begin_dialogs.length : 0;
    const toolsCount = (persona.tools && Array.isArray(persona.tools) && persona.tools.length) ? persona.tools.length : 0;
    const systemPrompt = (persona.system_prompt && typeof persona.system_prompt === 'string') ? persona.system_prompt : '暂无系统提示';
    
    card.innerHTML = `
        <div class="default-persona-content">
            <div class="persona-field">
                <label>系统提示:</label>
                <div class="persona-prompt-preview">${truncateText(systemPrompt, 200)}</div>
            </div>
            <div class="persona-field">
                <label>开始对话:</label>
                <div class="persona-dialogs-preview">${dialogsCount} 条对话</div>
            </div>
            <div class="persona-field">
                <label>工具:</label>
                <div class="persona-tools-preview">${toolsCount} 个工具</div>
            </div>
        </div>
    `;
}

// 绑定人格管理事件
function bindPersonaManagementEvents() {
    // 创建人格按钮
    const createBtn = document.getElementById('createPersonaBtn');
    if (createBtn) {
        createBtn.addEventListener('click', showCreatePersonaDialog);
    }
    
    // 导入人格按钮
    const importBtn = document.getElementById('importPersonaBtn');
    if (importBtn) {
        importBtn.addEventListener('click', showImportPersonaDialog);
    }
    
    // 刷新列表按钮
    const refreshBtn = document.getElementById('refreshPersonasBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadPersonaManagementData);
    }
}

// 显示创建人格对话框
function showCreatePersonaDialog() {
    const dialogHTML = `
        <div class="persona-dialog-overlay" id="personaDialogOverlay">
            <div class="persona-dialog">
                <div class="dialog-header">
                    <h3>创建新人格</h3>
                    <button class="close-btn" onclick="closePersonaDialog()">
                        <i class="material-icons">close</i>
                    </button>
                </div>
                <div class="dialog-content">
                    <form id="createPersonaForm">
                        <div class="form-group">
                            <label for="personaId">人格ID *</label>
                            <input type="text" id="personaId" required placeholder="输入唯一的人格ID">
                            <small class="form-hint">人格的唯一标识符，只能包含字母、数字、下划线和短横线</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="systemPrompt">系统提示 *</label>
                            <textarea id="systemPrompt" rows="8" required placeholder="输入系统提示词..."></textarea>
                            <small class="form-hint">定义人格的性格、行为和回应风格</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="beginDialogs">开始对话 (JSON数组)</label>
                            <textarea id="beginDialogs" rows="4" placeholder='[{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！很高兴见到你"}]'></textarea>
                            <small class="form-hint">定义人格的初始对话，JSON格式</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="tools">工具列表 (JSON数组)</label>
                            <textarea id="tools" rows="3" placeholder='["web_search", "calculator"]'></textarea>
                            <small class="form-hint">人格可以使用的工具列表，JSON格式</small>
                        </div>
                    </form>
                </div>
                <div class="dialog-actions">
                    <button class="btn btn-secondary" onclick="closePersonaDialog()">取消</button>
                    <button class="btn btn-primary" onclick="createPersona()">创建人格</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
    
    // 添加点击外部关闭功能
    const overlay = document.getElementById('personaDialogOverlay');
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closePersonaDialog();
        }
    });
}

// 显示编辑人格对话框
async function editPersona(personaId) {
    try {
        showSpinner(document.querySelector(`[data-persona-id="${personaId}"]`));
        
        const response = await fetch(`/api/persona_management/get/${personaId}`);
        if (!response.ok) {
            throw new Error('获取人格详情失败');
        }
        
        const persona = await response.json();
        
        // 创建备份（按照要求的命名格式：原人格名-年月日具体时间-备份）
        const now = new Date();
        const backupName = `${personaId}-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}-备份`;
        
        const dialogHTML = `
            <div class="persona-dialog-overlay" id="personaDialogOverlay">
                <div class="persona-dialog">
                    <div class="dialog-header">
                        <h3>编辑人格: ${personaId}</h3>
                        <button class="close-btn" onclick="closePersonaDialog()">
                            <i class="material-icons">close</i>
                        </button>
                    </div>
                    <div class="dialog-content">
                        <div class="backup-notice">
                            <i class="material-icons">info</i>
                            <span>保存时将自动备份为: ${backupName}</span>
                        </div>
                        <form id="editPersonaForm">
                            <input type="hidden" id="editPersonaId" value="${personaId}">
                            
                            <div class="form-group">
                                <label for="editSystemPrompt">系统提示 *</label>
                                <textarea id="editSystemPrompt" rows="8" required>${persona.system_prompt}</textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="editBeginDialogs">开始对话 (JSON数组)</label>
                                <textarea id="editBeginDialogs" rows="4">${JSON.stringify(persona.begin_dialogs, null, 2)}</textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="editTools">工具列表 (JSON数组)</label>
                                <textarea id="editTools" rows="3">${JSON.stringify(persona.tools, null, 2)}</textarea>
                            </div>
                        </form>
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" onclick="closePersonaDialog()">取消</button>
                        <button class="btn btn-primary" onclick="updatePersona()">保存修改</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', dialogHTML);
        
        // 添加点击外部关闭功能
        const overlay = document.getElementById('personaDialogOverlay');
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closePersonaDialog();
            }
        });
        
    } catch (error) {
        console.error('加载人格详情失败:', error);
        showError(`加载人格详情失败: ${error.message}`);
    } finally {
        hideSpinner(document.querySelector(`[data-persona-id="${personaId}"]`));
    }
}

// 创建人格
async function createPersona() {
    try {
        const personaId = document.getElementById('personaId').value.trim();
        const systemPrompt = document.getElementById('systemPrompt').value.trim();
        const beginDialogsText = document.getElementById('beginDialogs').value.trim();
        const toolsText = document.getElementById('tools').value.trim();
        
        if (!personaId || !systemPrompt) {
            showError('人格ID和系统提示不能为空');
            return;
        }
        
        // 解析JSON
        let beginDialogs = [];
        let tools = [];
        
        try {
            if (beginDialogsText) {
                beginDialogs = JSON.parse(beginDialogsText);
            }
            if (toolsText) {
                tools = JSON.parse(toolsText);
            }
        } catch (e) {
            showError('JSON格式错误，请检查开始对话和工具列表的格式');
            return;
        }
        
        const response = await fetch('/api/persona_management/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                persona_id: personaId,
                system_prompt: systemPrompt,
                begin_dialogs: beginDialogs,
                tools: tools
            })
        });
        
        if (response.ok) {
            showSuccess('人格创建成功');
            closePersonaDialog();
            // 立即更新人格数据
            await updatePersonaDataSilently();
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '创建人格失败');
        }
        
    } catch (error) {
        console.error('创建人格失败:', error);
        showError(`创建人格失败: ${error.message}`);
    }
}

// 更新人格
async function updatePersona() {
    try {
        const personaId = document.getElementById('editPersonaId').value;
        const systemPrompt = document.getElementById('editSystemPrompt').value.trim();
        const beginDialogsText = document.getElementById('editBeginDialogs').value.trim();
        const toolsText = document.getElementById('editTools').value.trim();
        
        if (!systemPrompt) {
            showError('系统提示不能为空');
            return;
        }
        
        // 解析JSON
        let beginDialogs = [];
        let tools = [];
        
        try {
            if (beginDialogsText) {
                beginDialogs = JSON.parse(beginDialogsText);
            }
            if (toolsText) {
                tools = JSON.parse(toolsText);
            }
        } catch (e) {
            showError('JSON格式错误，请检查开始对话和工具列表的格式');
            return;
        }
        
        // 先创建备份
        const now = new Date();
        const backupName = `${personaId}-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}-备份`;
        
        // 获取当前人格信息用于备份
        const currentPersona = currentPersonas.find(p => p.persona_id === personaId);
        if (currentPersona) {
            try {
                await fetch('/api/persona_management/create', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        persona_id: backupName,
                        system_prompt: currentPersona.system_prompt,
                        begin_dialogs: currentPersona.begin_dialogs,
                        tools: currentPersona.tools
                    })
                });
                console.log(`已创建备份: ${backupName}`);
            } catch (backupError) {
                console.warn('创建备份失败:', backupError);
            }
        }
        
        // 更新人格
        const response = await fetch(`/api/persona_management/update/${personaId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                system_prompt: systemPrompt,
                begin_dialogs: beginDialogs,
                tools: tools
            })
        });
        
        if (response.ok) {
            showSuccess('人格更新成功');
            closePersonaDialog();
            // 立即更新人格数据
            await updatePersonaDataSilently();
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '更新人格失败');
        }
        
    } catch (error) {
        console.error('更新人格失败:', error);
        showError(`更新人格失败: ${error.message}`);
    }
}

// 删除人格
async function deletePersona(personaId) {
    if (!confirm(`确定要删除人格 "${personaId}" 吗？此操作无法撤销。`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/persona_management/delete/${personaId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            showSuccess('人格删除成功');
            // 立即更新人格数据
            await updatePersonaDataSilently();
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '删除人格失败');
        }
        
    } catch (error) {
        console.error('删除人格失败:', error);
        showError(`删除人格失败: ${error.message}`);
    }
}

// 导出人格
async function exportPersona(personaId) {
    try {
        const response = await fetch(`/api/persona_management/export/${personaId}`);
        if (!response.ok) {
            throw new Error('导出人格失败');
        }
        
        const personaData = await response.json();
        
        // 创建下载链接
        const dataStr = JSON.stringify(personaData, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        
        const link = document.createElement('a');
        link.href = url;
        link.download = `persona-${personaId}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        
        showSuccess('人格导出成功');
        
    } catch (error) {
        console.error('导出人格失败:', error);
        showError(`导出人格失败: ${error.message}`);
    }
}

// 显示导入人格对话框
function showImportPersonaDialog() {
    const dialogHTML = `
        <div class="persona-dialog-overlay" id="personaDialogOverlay">
            <div class="persona-dialog">
                <div class="dialog-header">
                    <h3>导入人格</h3>
                    <button class="close-btn" onclick="closePersonaDialog()">
                        <i class="material-icons">close</i>
                    </button>
                </div>
                <div class="dialog-content">
                    <form id="importPersonaForm">
                        <div class="form-group">
                            <label for="personaFile">选择人格文件</label>
                            <input type="file" id="personaFile" accept=".json" onchange="handlePersonaFileSelect(event)">
                            <small class="form-hint">选择之前导出的人格JSON文件</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="importPersonaData">人格数据</label>
                            <textarea id="importPersonaData" rows="10" placeholder="或者直接粘贴人格JSON数据..."></textarea>
                        </div>
                        
                        <div class="form-group">
                            <label class="switch-label">
                                <input type="checkbox" id="overwritePersona">
                                <span class="switch-slider"></span>
                                覆盖已存在的人格
                            </label>
                            <small class="form-hint">如果人格ID已存在，是否覆盖现有人格</small>
                        </div>
                    </form>
                </div>
                <div class="dialog-actions">
                    <button class="btn btn-secondary" onclick="closePersonaDialog()">取消</button>
                    <button class="btn btn-primary" onclick="importPersona()">导入人格</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
    
    // 添加点击外部关闭功能
    const overlay = document.getElementById('personaDialogOverlay');
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closePersonaDialog();
        }
    });
}

// 处理人格文件选择
function handlePersonaFileSelect(event) {
    const file = event.target.files[0];
    if (file && file.type === 'application/json') {
        const reader = new FileReader();
        reader.onload = function(e) {
            try {
                const personaData = JSON.parse(e.target.result);
                document.getElementById('importPersonaData').value = JSON.stringify(personaData, null, 2);
            } catch (error) {
                showError('无效的JSON文件格式');
            }
        };
        reader.readAsText(file);
    } else {
        showError('请选择有效的JSON文件');
    }
}

// 导入人格
async function importPersona() {
    try {
        const personaDataText = document.getElementById('importPersonaData').value.trim();
        const overwrite = document.getElementById('overwritePersona').checked;
        
        if (!personaDataText) {
            showError('请选择文件或输入人格数据');
            return;
        }
        
        let personaData;
        try {
            personaData = JSON.parse(personaDataText);
        } catch (e) {
            showError('无效的JSON格式');
            return;
        }
        
        // 验证必需字段
        if (!personaData.persona_id || !personaData.system_prompt) {
            showError('人格数据缺少必需字段 (persona_id, system_prompt)');
            return;
        }
        
        personaData.overwrite = overwrite;
        
        const response = await fetch('/api/persona_management/import', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(personaData)
        });
        
        if (response.ok) {
            showSuccess('人格导入成功');
            closePersonaDialog();
            // 立即更新人格数据
            await updatePersonaDataSilently();
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || '导入人格失败');
        }
        
    } catch (error) {
        console.error('导入人格失败:', error);
        showError(`导入人格失败: ${error.message}`);
    }
}

// 关闭人格对话框
function closePersonaDialog() {
    const overlay = document.getElementById('personaDialogOverlay');
    if (overlay) {
        overlay.remove();
    }
}

// ========== 学习内容文本汇总功能 ==========

let allLearningContent = {
    dialogues: [],
    analysis: [],
    features: [],
    history: []
};

// 加载对话风格学习数据时也加载文本内容
async function loadStyleLearningData() {
    updateRefreshIndicator('加载中...');
    try {
        // 并行加载学习成果、模式数据和文本内容（文本内容使用缓存）
        const [resultsResponse, patternsResponse, contentResponse] = await Promise.all([
            fetch('/api/style_learning/results'),
            fetch('/api/style_learning/patterns'),
            fetch('/api/style_learning/content_text')  // 不加force_refresh，使用缓存
        ]);
        
        if (resultsResponse.ok && patternsResponse.ok) {
            const results = await resultsResponse.json();
            const patterns = await patternsResponse.json();
            
            // 检查是否有错误
            if (results.error) {
                throw new Error(results.error);
            }
            if (patterns.error) {
                throw new Error(patterns.error);
            }
            
            // 更新统计概览
            renderStyleLearningStats(results.statistics || {});
            
            // 初始化图表
            initializeStyleLearningCharts(results, patterns);
            
            // 更新学习模式列表
            renderLearningPatterns(patterns);
            
            // 加载学习内容文本
            if (contentResponse.ok) {
                const contentData = await contentResponse.json();
                allLearningContent = contentData || allLearningContent;
                renderAllLearningContent();
            } else {
                console.warn('加载学习内容文本失败，使用默认数据');
                loadFallbackLearningContent();
            }
            
            updateRefreshIndicator('刚刚更新');
        } else {
            const resultsText = await resultsResponse.text();
            const patternsText = await patternsResponse.text();
            console.error('API响应错误:', { resultsText, patternsText });
            throw new Error('获取风格学习数据失败');
        }
    } catch (error) {
        console.error('加载对话风格学习数据失败:', error);
        showError(`加载数据失败: ${error.message || '请检查网络连接'}`);
        updateRefreshIndicator('更新失败');
        
        // 加载备用内容
        loadFallbackLearningContent();
    }
}

// 加载所有学习内容文本（支持强制刷新参数）
async function loadAllLearningContent(forceRefresh = true) {
    try {
        updateRefreshIndicator('加载学习内容中...');

        // 添加force_refresh参数以强制刷新缓存
        const url = forceRefresh
            ? '/api/style_learning/content_text?force_refresh=true'
            : '/api/style_learning/content_text';

        const response = await fetch(url);
        if (response.ok) {
            const contentData = await response.json();
            allLearningContent = contentData || allLearningContent;
            renderAllLearningContent();
            showSuccess(forceRefresh ? '学习内容已强制刷新' : '学习内容已加载');
        } else {
            console.warn('无法从API加载内容，使用备用数据');
            loadFallbackLearningContent();
        }

        updateRefreshIndicator('刚刚更新');
    } catch (error) {
        console.error('加载学习内容失败:', error);
        showError('加载内容失败，请检查网络连接');
        loadFallbackLearningContent();
    }
}

// 加载备用学习内容（当API不可用时）
function loadFallbackLearningContent() {
    // 当API不可用时，显示空数据而不是示例数据
    allLearningContent = {
        dialogues: [],
        analysis: [],
        features: [],
        history: []
    };
    
    renderAllLearningContent();
}

// 渲染所有学习内容
function renderAllLearningContent() {
    renderContentCategory('dialogue-content', allLearningContent.dialogues, '对话示例');
    renderContentCategory('analysis-content', allLearningContent.analysis, '分析结果');
    renderContentCategory('features-content', allLearningContent.features, '风格特征');
    renderContentCategory('history-content', allLearningContent.history, '学习历程');
}

// 渲染单个内容类别
function renderContentCategory(containerId, content, categoryName) {
    const container = document.getElementById(containerId);
    
    if (!content || content.length === 0) {
        container.innerHTML = `<div class="no-content">暂无${categoryName}数据</div>`;
        return;
    }
    
    container.innerHTML = content.map(item => `
        <div class="content-item">
            <div class="content-timestamp">${item.timestamp || '未知时间'}</div>
            <div class="content-text">${item.text || '无内容'}</div>
            ${item.metadata ? `<div class="content-metadata">${item.metadata}</div>` : ''}
        </div>
    `).join('');
}

// 搜索和过滤学习内容
function filterLearningContent() {
    const searchTerm = document.getElementById('contentSearchInput').value.toLowerCase();
    const allItems = document.querySelectorAll('.content-item');
    
    allItems.forEach(item => {
        const text = item.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            item.style.display = 'block';
            // 高亮搜索词
            highlightSearchTerm(item, searchTerm);
        } else {
            item.style.display = 'none';
        }
    });
}

// 高亮搜索词
function highlightSearchTerm(element, searchTerm) {
    if (!searchTerm.trim()) {
        // 清除之前的高亮
        element.innerHTML = element.innerHTML.replace(/<mark class="highlight">/g, '').replace(/<\/mark>/g, '');
        return;
    }
    
    const textNodes = element.querySelectorAll('.content-text');
    textNodes.forEach(node => {
        const originalText = node.textContent;
        const highlightedText = originalText.replace(
            new RegExp(`(${searchTerm})`, 'gi'),
            '<mark class="highlight">$1</mark>'
        );
        node.innerHTML = highlightedText;
    });
}

// 导出学习内容
function exportLearningContent() {
    showExportDialog();
}

// 显示导出对话框
function showExportDialog() {
    const dialogHTML = `
        <div class="export-dialog" id="exportDialog">
            <div class="export-dialog-content">
                <h3>导出学习内容</h3>
                <p>选择要导出的内容格式：</p>
                
                <div class="export-format-options">
                    <label class="format-option">
                        <input type="radio" name="exportFormat" value="json" checked>
                        <span>JSON格式 - 包含所有数据和元信息</span>
                    </label>
                    <label class="format-option">
                        <input type="radio" name="exportFormat" value="txt">
                        <span>纯文本格式 - 仅包含学习内容文本</span>
                    </label>
                    <label class="format-option">
                        <input type="radio" name="exportFormat" value="markdown">
                        <span>Markdown格式 - 结构化文档</span>
                    </label>
                </div>
                
                <div class="dialog-actions">
                    <button class="btn btn-secondary" onclick="closeExportDialog()">取消</button>
                    <button class="btn btn-primary" onclick="performExport()">导出</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
    
    // 添加点击外部关闭功能
    const overlay = document.getElementById('exportDialog');
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeExportDialog();
        }
    });
}

// 关闭导出对话框
function closeExportDialog() {
    const dialog = document.getElementById('exportDialog');
    if (dialog) {
        dialog.remove();
    }
}

// 执行导出
function performExport() {
    const selectedFormat = document.querySelector('input[name="exportFormat"]:checked').value;
    let content = '';
    let filename = '';
    let mimeType = '';
    
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    
    switch (selectedFormat) {
        case 'json':
            content = JSON.stringify(allLearningContent, null, 2);
            filename = `learning-content-${timestamp}.json`;
            mimeType = 'application/json';
            break;
            
        case 'txt':
            content = formatAsText(allLearningContent);
            filename = `learning-content-${timestamp}.txt`;
            mimeType = 'text/plain';
            break;
            
        case 'markdown':
            content = formatAsMarkdown(allLearningContent);
            filename = `learning-content-${timestamp}.md`;
            mimeType = 'text/markdown';
            break;
    }
    
    // 创建下载链接
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    
    closeExportDialog();
    showSuccess('学习内容已导出');
}

// 格式化为纯文本
function formatAsText(content) {
    let text = '对话风格学习内容汇总\n';
    text += '='.repeat(30) + '\n\n';
    
    if (content.dialogues && content.dialogues.length > 0) {
        text += '【对话示例文本】\n';
        content.dialogues.forEach(item => {
            text += `时间: ${item.timestamp}\n`;
            text += `内容: ${item.text}\n`;
            if (item.metadata) text += `备注: ${item.metadata}\n`;
            text += '\n';
        });
        text += '\n';
    }
    
    if (content.analysis && content.analysis.length > 0) {
        text += '【学习分析结果】\n';
        content.analysis.forEach(item => {
            text += `时间: ${item.timestamp}\n`;
            text += `内容: ${item.text}\n`;
            if (item.metadata) text += `备注: ${item.metadata}\n`;
            text += '\n';
        });
        text += '\n';
    }
    
    if (content.features && content.features.length > 0) {
        text += '【提炼的风格特征】\n';
        content.features.forEach(item => {
            text += `时间: ${item.timestamp}\n`;
            text += `内容: ${item.text}\n`;
            if (item.metadata) text += `备注: ${item.metadata}\n`;
            text += '\n';
        });
        text += '\n';
    }
    
    if (content.history && content.history.length > 0) {
        text += '【学习历程记录】\n';
        content.history.forEach(item => {
            text += `时间: ${item.timestamp}\n`;
            text += `内容: ${item.text}\n`;
            if (item.metadata) text += `备注: ${item.metadata}\n`;
            text += '\n';
        });
    }
    
    return text;
}

// 格式化为Markdown
function formatAsMarkdown(content) {
    let md = '# 对话风格学习内容汇总\n\n';
    
    if (content.dialogues && content.dialogues.length > 0) {
        md += '## 对话示例文本\n\n';
        content.dialogues.forEach(item => {
            md += `### ${item.timestamp}\n\n`;
            md += '```\n';
            md += item.text + '\n';
            md += '```\n\n';
            if (item.metadata) md += `**备注:** ${item.metadata}\n\n`;
        });
    }
    
    if (content.analysis && content.analysis.length > 0) {
        md += '## 学习分析结果\n\n';
        content.analysis.forEach(item => {
            md += `### ${item.timestamp}\n\n`;
            md += item.text + '\n\n';
            if (item.metadata) md += `**备注:** ${item.metadata}\n\n`;
        });
    }
    
    if (content.features && content.features.length > 0) {
        md += '## 提炼的风格特征\n\n';
        content.features.forEach(item => {
            md += `### ${item.timestamp}\n\n`;
            md += item.text + '\n\n';
            if (item.metadata) md += `**备注:** ${item.metadata}\n\n`;
        });
    }
    
    if (content.history && content.history.length > 0) {
        md += '## 学习历程记录\n\n';
        content.history.forEach(item => {
            md += `### ${item.timestamp}\n\n`;
            md += item.text + '\n\n';
            if (item.metadata) md += `**备注:** ${item.metadata}\n\n`;
        });
    }
    
    return md;
}

// 工具函数
function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '--';
    try {
        const date = new Date(dateTimeStr);
        return date.toLocaleString();
    } catch (e) {
        return dateTimeStr;
    }
}

// ==================== 审查页面功能 ====================

// 初始化审查页面选项卡
function initializeReviewTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const filterBtns = document.querySelectorAll('.filter-btn');

    // 选项卡切换
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.getAttribute('data-tab');
            
            // 更新选项卡按钮状态
            tabBtns.forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            
            // 显示对应内容
            tabContents.forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabName}-content`).classList.add('active');
            
            // 加载对应数据
            if (tabName === 'pending') {
                loadPendingReviews();
            } else if (tabName === 'reviewed') {
                loadReviewedPersonaUpdates();
            }
        });
    });

    // 过滤按钮
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(f => f.classList.remove('active'));
            btn.classList.add('active');
            
            const filter = btn.getAttribute('data-filter');
            filterReviewedList(filter);
        });
    });
}

// 加载待审查的列表
async function loadPendingReviews() {
    try {
        const response = await fetch('/api/persona_updates');
        const data = await response.json();
        
        if (data.success) {
            renderPersonaUpdates(data.updates);
            await updateReviewStats(data.updates);
        } else {
            showError('加载待审查列表失败');
        }
    } catch (error) {
        console.error('加载待审查列表失败:', error);
        showError('加载待审查列表失败');
    }
}

// 加载已审查的人格更新列表
async function loadReviewedPersonaUpdates() {
    try {
        const response = await fetch('/api/persona_updates/reviewed');
        const data = await response.json();
        
        if (data.success) {
            renderReviewedPersonaUpdates(data.updates);
        } else {
            showError('加载审查历史失败');
        }
    } catch (error) {
        console.error('加载审查历史失败:', error);
        showError('加载审查历史失败');
    }
}

// 渲染已审查的人格更新列表
function renderReviewedPersonaUpdates(updates) {
    const reviewedList = document.getElementById('reviewed-list');
    
    if (!updates || updates.length === 0) {
        reviewedList.innerHTML = '<div class="no-updates">暂无审查历史</div>';
        return;
    }
    
    // 清空列表
    reviewedList.innerHTML = '';
    
    // 为每个更新创建元素并绑定事件
    updates.forEach(update => {
        const updateElement = document.createElement('div');
        updateElement.className = `persona-update-item reviewed-item ${update.status}`;
        updateElement.setAttribute('data-status', update.status);
        
        const statusIcon = update.status === 'approved' ? 'check_circle' : 'cancel';
        const statusText = update.status === 'approved' ? '已批准' : '已拒绝';
        const statusClass = update.status === 'approved' ? 'status-approved' : 'status-rejected';
        
        // 确定更新类型和对应的徽章 - 使用 review_source 字段
        const reviewSource = update.review_source || '';
        let typeBadge = '';
        let typeText = '';

        if (reviewSource === 'style_learning') {
            typeBadge = '<span class="type-badge style-badge">风格学习</span>';
            typeText = '风格学习更新';
        } else if (reviewSource === 'persona_learning') {
            typeBadge = '<span class="type-badge persona-badge">人格学习</span>';
            typeText = '人格学习更新';
        } else {
            typeBadge = '<span class="type-badge general-badge">常规更新</span>';
            typeText = '常规更新';
        }
        
        updateElement.innerHTML = `
            ${typeBadge}
            <div class="update-header">
                <div class="update-checkbox">
                    <input type="checkbox" class="reviewed-checkbox" value="${update.id}" id="reviewed-${update.id}">
                    <label for="reviewed-${update.id}"></label>
                </div>
                <div class="update-info">
                    <div class="update-id-badge">
                        <span class="id-badge">${update.id}</span>
                    </div>
                </div>
                <div class="status-badge ${statusClass}">
                    <i class="material-icons">${statusIcon}</i>
                    ${statusText}
                </div>
            </div>
            <div class="update-content">
                <div class="review-info">
                    <p><strong>原因:</strong> ${update.reason || '未提供'}</p>
                    <p><strong>审查时间:</strong> ${update.review_time ? new Date(update.review_time * 1000).toLocaleString() : '未知'}</p>
                    <p><strong>置信度:</strong> ${(update.confidence_score * 100).toFixed(1)}%</p>
                    ${update.reviewer_comment ? `<p><strong>审查备注:</strong> ${update.reviewer_comment}</p>` : ''}
                </div>
                <div class="update-preview">
                    <p><strong>原始内容:</strong> <button class="toggle-content-btn" data-target="reviewed-original-${update.id}">展开完整内容</button></p>
                    <div class="content-preview" id="reviewed-original-${update.id}" data-collapsed="true"></div>
                    <div class="content-preview full-content" id="reviewed-original-full-${update.id}" style="display: none;"></div>

                    <p><strong>建议更新:</strong> <button class="toggle-content-btn" data-target="reviewed-proposed-${update.id}">展开完整内容</button></p>
                    <div class="content-preview highlighted-diff" id="reviewed-proposed-${update.id}" data-collapsed="true"></div>
                    <div class="content-preview full-content highlighted-diff" id="reviewed-proposed-full-${update.id}" style="display: none;"></div>
                </div>
            </div>
            <div class="update-actions">
                <button class="btn btn-warning revert-btn">
                    <i class="material-icons">undo</i>
                    撤回${update.status === 'approved' ? '批准' : '拒绝'}
                </button>
                <button class="btn btn-secondary view-detail-btn">
                    <i class="material-icons">info</i>
                    查看详情
                </button>
                <button class="btn btn-danger delete-btn">
                    <i class="material-icons">delete</i>
                    删除
                </button>
            </div>
        `;
        
        // 绑定事件处理器
        const revertBtn = updateElement.querySelector('.revert-btn');
        const viewDetailBtn = updateElement.querySelector('.view-detail-btn');
        const deleteBtn = updateElement.querySelector('.delete-btn');
        const toggleBtns = updateElement.querySelectorAll('.toggle-content-btn');
        
        revertBtn.addEventListener('click', () => revertReview(update.id, update.status));
        viewDetailBtn.addEventListener('click', () => viewReviewDetail(update));
        deleteBtn.addEventListener('click', () => deletePersonaUpdate(update.id));
        
        // 添加复选框变化监听器
        const checkbox = updateElement.querySelector('.reviewed-checkbox');
        if (checkbox) {
            checkbox.addEventListener('change', updateBatchOperationsVisibility);
        }
        
        // 绑定展开/收起按钮
        toggleBtns.forEach(btn => {
            btn.addEventListener('click', (e) => toggleContentView(e.target));
        });

        // 应用高亮和格式化到已审查的内容
        const reviewedProposedShortDiv = updateElement.querySelector(`#reviewed-proposed-${update.id}`);
        const reviewedProposedFullDiv = updateElement.querySelector(`#reviewed-proposed-full-${update.id}`);
        const reviewedOriginalShortDiv = updateElement.querySelector(`#reviewed-original-${update.id}`);
        const reviewedOriginalFullDiv = updateElement.querySelector(`#reviewed-original-full-${update.id}`);

        if (reviewedProposedShortDiv && reviewedProposedFullDiv) {
            // 检查是否只是key_change更新
            const isKeyChangeOnly = update.proposed_content && update.proposed_content.length < 500;

            // 生成高亮的内容
            const highlightedFullContent = highlightTextDifferences(
                update.original_content || '',
                update.proposed_content || '',
                isKeyChangeOnly
            );

            const truncatedProposed = truncateText(update.proposed_content || '', 200);
            const highlightedShortContent = highlightTextDifferences(
                update.original_content || '',
                truncatedProposed,
                isKeyChangeOnly
            );

            reviewedProposedShortDiv.innerHTML = highlightedShortContent;
            reviewedProposedFullDiv.innerHTML = highlightedFullContent;
        }

        if (reviewedOriginalShortDiv && reviewedOriginalFullDiv) {
            // 格式化原始内容的换行符
            reviewedOriginalShortDiv.innerHTML = formatNewlines(truncateText(update.original_content || '', 200));
            reviewedOriginalFullDiv.innerHTML = formatNewlines(update.original_content || '');
        }

        reviewedList.appendChild(updateElement);
    });
}

// 过滤已审查列表
function filterReviewedList(filter) {
    const reviewedItems = document.querySelectorAll('.reviewed-item');
    
    reviewedItems.forEach(item => {
        const status = item.getAttribute('data-status');
        
        if (filter === 'all') {
            item.style.display = 'block';
        } else if (filter === 'approved' && status === 'approved') {
            item.style.display = 'block';
        } else if (filter === 'rejected' && status === 'rejected') {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// 撤回审查操作
async function revertReview(updateId, currentStatus) {
    const actionText = currentStatus === 'approved' ? '批准' : '拒绝';
    
    if (!confirm(`确定要撤回${actionText}操作吗？撤回后该更新将重新回到待审查列表。`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/persona_updates/${updateId}/revert`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                reason: `撤回${actionText}操作`
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSuccess(`成功撤回${actionText}操作`);
            // 重新加载已审查列表
            loadReviewedPersonaUpdates();
            // 更新统计信息
            loadPendingReviews();
        } else {
            showError(data.error || `撤回${actionText}操作失败`);
        }
    } catch (error) {
        console.error('撤回操作失败:', error);
        showError('撤回操作失败');
    }
}

// 查看审查详情
function viewReviewDetail(update) {
    const dialogHTML = `
        <div class="persona-edit-overlay" id="reviewDetailOverlay">
            <div class="persona-edit-dialog">
                <div class="dialog-header">
                    <h3>审查详情 - ID: ${update.id}</h3>
                    <button class="close-btn" id="closeDetailDialogBtn">
                        <i class="material-icons">close</i>
                    </button>
                </div>
                <div class="dialog-content">
                    <div class="detail-info">
                        <div class="info-section">
                            <h4>基本信息</h4>
                            <p><strong>更新类型:</strong> ${update.update_type || '人格更新'}</p>
                            <p><strong>置信度:</strong> ${(update.confidence_score * 100).toFixed(1)}%</p>
                            <p><strong>原因:</strong> ${update.reason || '未提供'}</p>
                            <p><strong>创建时间:</strong> ${new Date(update.timestamp * 1000).toLocaleString()}</p>
                            ${update.total_raw_messages ? `<p><strong>样本总数:</strong> ${update.total_raw_messages} 条原始消息</p>` : ''}
                            ${update.messages_analyzed ? `<p><strong>分析样本:</strong> ${update.messages_analyzed} 条筛选消息</p>` : ''}
                        </div>

                        <div class="info-section">
                            <h4>审查信息</h4>
                            <p><strong>审查状态:</strong> <span class="status-badge ${update.status === 'approved' ? 'status-approved' : 'status-rejected'}">${update.status === 'approved' ? '已批准' : '已拒绝'}</span></p>
                            <p><strong>审查时间:</strong> ${update.review_time ? new Date(update.review_time * 1000).toLocaleString() : '未知'}</p>
                            ${update.reviewer_comment ? `<p><strong>审查备注:</strong> ${update.reviewer_comment}</p>` : '<p><strong>审查备注:</strong> 无</p>'}
                        </div>

                        ${update.features_content ? `
                        <div class="content-section">
                            <h4><i class="material-icons">analytics</i> 提炼的风格特征</h4>
                            <div class="content-display" style="background-color: #f5f7fa; font-family: 'Courier New', monospace; white-space: pre-wrap;">${update.features_content}</div>
                        </div>
                        ` : ''}

                        <div class="content-section">
                            <h4>原始人格内容</h4>
                            <div class="content-display">${update.original_content || '无内容'}</div>
                        </div>

                        <div class="content-section">
                            <h4>建议更新内容</h4>
                            <div class="content-display">${update.proposed_content || '无内容'}</div>
                        </div>
                    </div>
                </div>
                <div class="dialog-actions">
                    <button class="btn btn-secondary" id="closeDetailBtn">
                        <i class="material-icons">close</i>
                        关闭
                    </button>
                    <button class="btn btn-warning" id="revertDetailBtn">
                        <i class="material-icons">undo</i>
                        撤回${update.status === 'approved' ? '批准' : '拒绝'}
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 添加对话框到页面
    document.body.insertAdjacentHTML('beforeend', dialogHTML);
    
    // 绑定事件处理器
    const overlay = document.getElementById('reviewDetailOverlay');
    const closeBtn = document.getElementById('closeDetailDialogBtn');
    const closeDetailBtn = document.getElementById('closeDetailBtn');
    const revertDetailBtn = document.getElementById('revertDetailBtn');
    
    // 关闭对话框事件
    const closeDialog = () => {
        overlay.remove();
    };
    
    closeBtn.addEventListener('click', closeDialog);
    closeDetailBtn.addEventListener('click', closeDialog);
    revertDetailBtn.addEventListener('click', () => {
        closeDialog();
        revertReview(update.id, update.status);
    });
    
    // 添加点击外部关闭功能
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeDialog();
        }
    });
}

// 修改原有的reviewUpdate函数，审查完成后刷新列表
const originalReviewUpdate = window.reviewUpdate;
if (originalReviewUpdate) {
    window.reviewUpdate = async function(updateId, action) {
        const result = await originalReviewUpdate(updateId, action);
        
        // 审查完成后，重新加载待审查列表和已审查列表
        if (result !== false) {
            setTimeout(() => {
                loadPendingReviews();
                // 如果当前在审查历史页面，也刷新已审查列表
                if (document.querySelector('#reviewed-tab.active')) {
                    loadReviewedPersonaUpdates();
                }
            }, 500);
        }
        
        return result;
    };
}

// 修改原有的reviewPersonaUpdate函数
const originalReviewPersonaUpdate = window.reviewPersonaUpdate;
if (originalReviewPersonaUpdate) {
    window.reviewPersonaUpdate = async function(updateId, action) {
        const result = await originalReviewPersonaUpdate(updateId, action);
        
        // 关闭编辑对话框
        if (typeof closePersonaEditDialog === 'function') {
            closePersonaEditDialog();
        }
        
        // 审查完成后，重新加载待审查列表和已审查列表
        if (result !== false) {
            setTimeout(() => {
                loadPendingReviews();
                // 如果当前在审查历史页面，也刷新已审查列表
                if (document.querySelector('#reviewed-tab.active')) {
                    loadReviewedPersonaUpdates();
                }
            }, 500);
        }
        
        return result;
    };
}

// 触发重新学习函数
async function triggerRelearn() {
    const relearnBtn = document.getElementById('relearnBtn');
    if (!relearnBtn) return;
    
    // 显示确认对话框
    if (!confirm('确定要重新学习所有历史消息吗？\n\n这将重置所有学习状态并重新处理所有消息数据，可能需要较长时间。')) {
        return;
    }
    
    // 设置按钮为加载状态
    const originalText = relearnBtn.innerHTML;
    relearnBtn.disabled = true;
    relearnBtn.classList.add('loading');
    relearnBtn.innerHTML = '<i class="material-icons">refresh</i><span>学习中...</span>';
    
    try {
        console.log('开始触发重新学习...');
        
        const response = await fetch('/api/relearn', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showNotification(
                `重新学习已启动！将处理 ${result.total_messages} 条历史消息`, 
                'success'
            );
            
            // 延迟刷新仪表板数据
            setTimeout(() => {
                if (typeof refreshDashboard === 'function') {
                    refreshDashboard();
                }
            }, 2000);
        } else {
            const errorMsg = result.error || '重新学习启动失败';
            showNotification(`启动失败: ${errorMsg}`, 'error');
            console.error('重新学习启动失败:', result);
        }
        
    } catch (error) {
        console.error('重新学习请求失败:', error);
        showNotification(`请求失败: ${error.message}`, 'error');
    } finally {
        // 恢复按钮状态
        relearnBtn.disabled = false;
        relearnBtn.classList.remove('loading');
        relearnBtn.innerHTML = originalText;
    }
}

// ==================== 社交关系分析相关函数 ====================

// 全局变量存储当前选中的群组数据
let currentGroupRelations = null;
let currentGroupId = null;
let relationshipChartInstance = null;  // 存储关系图表实例
let relationshipChartResizeHandler = null;  // 存储resize处理函数
let filteredUserId = null;  // 当前筛选的用户ID
let loadGroupRelationsController = null;  // AbortController用于取消请求

/**
 * 触发智能社交关系分析
 */
async function analyzeGroupRelations(event) {
    if (!currentGroupId) {
        showNotification('请先选择一个群组', 'warning');
        return;
    }

    // 获取按钮元素 - 如果event不存在,通过document查找
    const btn = event ? event.target.closest('button') : document.querySelector('button[onclick*="analyzeGroupRelations"]');
    if (!btn) {
        console.error('无法找到分析按钮元素');
        return;
    }

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="material-icons rotating">psychology</i> 分析中...';

    try {
        showNotification('正在使用LLM智能分析群组社交关系，请稍候...', 'info');

        const response = await fetch(`/api/social_relations/${currentGroupId}/analyze`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message_limit: 200,
                force_refresh: true
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '分析失败');
        }

        showNotification(`成功分析 ${data.relation_count} 条社交关系！`, 'success');

        // 重新加载关系数据 - 添加null检查
        const groupNameElement = document.getElementById('current-group-name');
        const groupName = groupNameElement?.textContent.replace(' 的成员关系', '') || '';
        await loadGroupRelations(currentGroupId, groupName);

    } catch (error) {
        console.error('分析社交关系失败:', error);
        showNotification(`分析失败: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * 清空群组关系数据（带二次确认）
 */
async function clearGroupRelations(event) {
    if (!currentGroupId) {
        showNotification('请先选择一个群组', 'warning');
        return;
    }

    // 第一次确认
    const groupNameElement = document.getElementById('current-group-name');
    const groupName = groupNameElement?.textContent.replace(' 的成员关系', '') || currentGroupId;

    const firstConfirm = confirm(`确定要清空群组 "${groupName}" 的所有人际关系数据吗？\n\n此操作不可恢复！`);
    if (!firstConfirm) {
        return;
    }

    // 第二次确认
    const secondConfirm = confirm(`⚠️ 最后确认 ⚠️\n\n您即将永久删除群组 "${groupName}" 的所有人际关系数据。\n\n请输入"确认删除"后点击确定，或点击取消放弃操作。`);
    if (!secondConfirm) {
        showNotification('已取消清空操作', 'info');
        return;
    }

    // 获取按钮元素
    const btn = event ? event.target.closest('button') : document.querySelector('button[onclick*="clearGroupRelations"]');
    if (!btn) {
        console.error('无法找到清空按钮元素');
        return;
    }

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="material-icons rotating">delete_forever</i> 清空中...';

    try {
        const response = await fetch(`/api/social_relations/${currentGroupId}/clear`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '清空失败');
        }

        showNotification(`成功清空 ${data.deleted_count || 0} 条关系数据！`, 'success');

        // 重新加载关系数据（此时应该为空）
        const groupNameForReload = groupNameElement?.textContent.replace(' 的成员关系', '') || '';
        await loadGroupRelations(currentGroupId, groupNameForReload);

    } catch (error) {
        console.error('清空社交关系失败:', error);
        showNotification(`清空失败: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

/**
 * 筛选指定用户的关系
 */
async function filterRelationsByUser() {
    const select = document.getElementById('user-filter-select');
    if (!select) {
        console.warn('用户筛选下拉框不存在');
        return;
    }

    filteredUserId = select.value;

    if (!currentGroupRelations) {
        return;
    }

    // 重新渲染关系图谱（会根据filteredUserId自动筛选）
    renderRelationshipChart(currentGroupRelations);
}

/**
 * 加载群组列表
 */
async function loadGroupList() {
    const container = document.getElementById('group-list-container');
    if (!container) return;

    container.innerHTML = '<div class="loading-message">正在加载群组列表...</div>';

    try {
        const response = await fetch('/api/social_relations/groups');
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '加载群组列表失败');
        }

        if (!data.groups || data.groups.length === 0) {
            container.innerHTML = '<div class="empty-message"><i class="material-icons">info</i><p>暂无群组数据</p></div>';
            return;
        }

        // 渲染群组列表
        let html = '<div class="group-cards">';
        data.groups.forEach(group => {
            html += `
                <div class="group-card" onclick="loadGroupRelations('${group.group_id}', '${escapeHtml(group.group_name || group.group_id)}')">
                    <div class="group-card-header">
                        <i class="material-icons">groups</i>
                        <h4>${escapeHtml(group.group_name || group.group_id)}</h4>
                    </div>
                    <div class="group-card-body">
                        <div class="group-stat">
                            <span class="stat-label">群组ID:</span>
                            <span class="stat-value">${group.group_id}</span>
                        </div>
                        <div class="group-stat">
                            <span class="stat-label">成员数:</span>
                            <span class="stat-value">${group.member_count || 0}</span>
                        </div>
                        <div class="group-stat">
                            <span class="stat-label">关系数:</span>
                            <span class="stat-value">${group.relation_count || 0}</span>
                        </div>
                        <div class="group-stat">
                            <span class="stat-label">消息数:</span>
                            <span class="stat-value">${group.message_count || 0}</span>
                        </div>
                    </div>
                    <div class="group-card-footer">
                        <button class="btn btn-primary btn-sm">
                            <i class="material-icons">visibility</i>
                            查看关系
                        </button>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        container.innerHTML = html;
    } catch (error) {
        console.error('加载群组列表失败:', error);
        container.innerHTML = `<div class="error-message"><i class="material-icons">error</i><p>加载失败: ${error.message}</p></div>`;
    }
}

/**
 * 加载指定群组的关系数据
 */
async function loadGroupRelations(groupId, groupName) {
    currentGroupId = groupId;

    // 取消之前的请求
    if (loadGroupRelationsController) {
        loadGroupRelationsController.abort();
    }
    loadGroupRelationsController = new AbortController();

    // 验证DOM元素存在
    const relationshipDetail = document.getElementById('relationship-detail');
    const groupListSection = document.querySelector('.group-list-section');

    if (!relationshipDetail || !groupListSection) {
        console.warn('社交关系页面元素不存在，可能用户已离开该页面');
        return;
    }

    // 显示关系详情区域，隐藏群组列表
    groupListSection.style.display = 'none';
    relationshipDetail.style.display = 'block';

    const groupNameElement = document.getElementById('current-group-name');
    if (groupNameElement) {
        groupNameElement.textContent = `${groupName} 的成员关系`;
    }

    // 显示加载状态 - 先销毁可能存在的ECharts实例
    const chartContainer = document.getElementById('relationship-graph-chart');
    if (chartContainer) {
        // 销毁已存在的ECharts实例，避免内存泄漏
        const existingChart = echarts.getInstanceByDom(chartContainer);
        if (existingChart) {
            existingChart.dispose();
        }
        chartContainer.innerHTML = '<div class="loading-message">正在加载关系数据...</div>';
    }

    try {
        const response = await fetch(`/api/social_relations/${groupId}`, {
            signal: loadGroupRelationsController.signal
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '加载关系数据失败');
        }

        // 异步操作完成后，再次验证元素是否仍然存在
        const stillOnPage = document.getElementById('relationship-detail');
        if (!stillOnPage || stillOnPage.style.display === 'none') {
            console.log('用户已离开社交关系页面，取消数据渲染');
            return;
        }

        currentGroupRelations = data;

        // 更新用户筛选下拉列表
        updateUserFilterSelect(data.members || []);

        // 更新统计数据
        updateRelationshipStats(data);

        // 渲染关系图谱
        renderRelationshipChart(data);

        // 渲染成员列表
        renderMembersList(data);

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('加载关系数据被取消');
            return;
        }

        console.error('加载群组关系失败:', error);
        if (chartContainer) {
            chartContainer.innerHTML = `<div class="error-message"><i class="material-icons">error</i><p>加载失败: ${error.message}</p></div>`;
        }
        showNotification(`加载失败: ${error.message}`, 'error');
    }
}

/**
 * 更新用户筛选下拉列表
 */
function updateUserFilterSelect(members) {
    const select = document.getElementById('user-filter-select');
    if (!select) return;

    // 清空旧选项
    select.innerHTML = '<option value="">显示所有用户关系</option>';

    // 添加用户选项
    members.forEach(member => {
        const option = document.createElement('option');
        option.value = member.user_id;
        option.textContent = `${member.nickname || member.user_id} (${member.message_count} 条消息)`;
        select.appendChild(option);
    });

    // 重置筛选状态
    filteredUserId = null;
}

/**
 * 更新关系统计数据
 */
function updateRelationshipStats(data) {
    const members = data.members || [];
    const relations = data.relations || [];

    // 总成员数 - 添加null检查
    const totalMembersEl = document.getElementById('total-members-count');
    if (totalMembersEl) totalMembersEl.textContent = members.length;

    // 总关系数 - 添加null检查
    const totalRelationsEl = document.getElementById('total-relations-count');
    if (totalRelationsEl) totalRelationsEl.textContent = relations.length;

    // 最活跃成员（基于关系数量）
    let mostActive = '--';
    if (members.length > 0) {
        const relationCounts = {};
        relations.forEach(rel => {
            relationCounts[rel.source] = (relationCounts[rel.source] || 0) + 1;
            relationCounts[rel.target] = (relationCounts[rel.target] || 0) + 1;
        });

        let maxCount = 0;
        let maxUserId = null;
        for (const [userId, count] of Object.entries(relationCounts)) {
            if (count > maxCount) {
                maxCount = count;
                maxUserId = userId;
            }
        }

        if (maxUserId) {
            const member = members.find(m => m.user_id === maxUserId);
            mostActive = member ? (member.nickname || member.user_id) : maxUserId;
        }
    }
    const mostActiveEl = document.getElementById('most-active-member');
    if (mostActiveEl) mostActiveEl.textContent = mostActive;

    // 平均关系强度
    let avgStrength = 0;
    if (relations.length > 0) {
        const totalStrength = relations.reduce((sum, rel) => sum + (rel.strength || 0), 0);
        avgStrength = (totalStrength / relations.length).toFixed(2);
    }
    const avgStrengthEl = document.getElementById('avg-relation-strength');
    if (avgStrengthEl) avgStrengthEl.textContent = avgStrength;
}

/**
 * 渲染关系图谱
 */
function renderRelationshipChart(data) {
    const chartDom = document.getElementById('relationship-graph-chart');
    if (!chartDom) return;

    // 安全销毁已存在的实例，避免内存泄漏和渲染冲突
    try {
        let existingChart = echarts.getInstanceByDom(chartDom);
        if (existingChart) {
            // 检查DOM元素是否仍然有效
            if (chartDom.parentNode) {
                existingChart.dispose();
            } else {
                // 如果DOM已被移除，只需清除引用
                console.warn('图表DOM已被移除，跳过dispose');
            }
        }
    } catch (e) {
        console.warn('销毁图表实例时出错:', e);
    }

    // 再次检查DOM是否仍然存在
    if (!document.getElementById('relationship-graph-chart')) {
        console.warn('图表DOM元素不存在，跳过渲染');
        return;
    }

    // 重新初始化
    let myChart = echarts.init(chartDom);

    const members = data.members || [];
    let relations = data.relations || [];

    // 如果有筛选用户，只显示该用户相关的关系
    if (filteredUserId) {
        relations = relations.filter(rel =>
            rel.source === filteredUserId || rel.target === filteredUserId
        );

        // 也只显示相关的节点
        const relatedUserIds = new Set();
        relatedUserIds.add(filteredUserId);
        relations.forEach(rel => {
            relatedUserIds.add(rel.source);
            relatedUserIds.add(rel.target);
        });

        // 筛选节点
        const filteredMembers = members.filter(m => relatedUserIds.has(m.user_id));

        // 构建节点数据（使用筛选后的成员）
        const nodes = filteredMembers.map(member => ({
            id: member.user_id,
            name: member.nickname || member.user_id,
            symbolSize: member.user_id === filteredUserId ? 50 : (30 + (member.message_count || 0) * 0.1),
            label: {
                show: true,
                fontWeight: member.user_id === filteredUserId ? 'bold' : 'normal'
            },
            itemStyle: {
                color: member.user_id === filteredUserId ? '#ff4757' : getNodeColor(member.message_count || 0)
            }
        }));

        // 构建边数据
        const links = relations.map(rel => ({
            source: rel.source,
            target: rel.target,
            value: rel.strength || 1,
            label: {
                show: true,
                formatter: rel.type_text || ''
            },
            lineStyle: {
                width: Math.max(1, (rel.strength || 0) * 2),
                opacity: 0.5 + (rel.strength || 0) * 0.3
            }
        }));

        // 保存当前数据供3D模式使用
        currentRelationsData = { nodes, links };

        renderFilteredChart(nodes, links, `${filteredMembers.find(m => m.user_id === filteredUserId)?.nickname || filteredUserId} 的社交关系`);
    } else {
        // 显示所有关系
        // 构建节点数据
        const nodes = members.map(member => ({
            id: member.user_id,
            name: member.nickname || member.user_id,
            symbolSize: 30 + (member.message_count || 0) * 0.1, // 根据消息数量调整节点大小
            label: {
                show: true
            },
            itemStyle: {
                color: getNodeColor(member.message_count || 0)
            }
        }));

        // 构建边数据
        const links = relations.map(rel => ({
            source: rel.source,
            target: rel.target,
            value: rel.strength || 1,
            lineStyle: {
                width: Math.max(1, (rel.strength || 0) * 2),
                opacity: 0.3 + (rel.strength || 0) * 0.3
            }
        }));

        // 保存当前数据供3D模式使用
        currentRelationsData = { nodes, links };

        renderFilteredChart(nodes, links, `${members.length} 个成员，${relations.length} 个关系连接`);
    }

    // 如果当前是3D模式，同步更新3D图谱
    if (currentGraphMode === '3d' && socialGraph3D && currentRelationsData) {
        load3DGraphData(currentRelationsData);
    }
}

/**
 * 渲染筛选后的图表
 */
function renderFilteredChart(nodes, links, title) {
    const chartDom = document.getElementById('relationship-graph-chart');
    if (!chartDom) return;

    // 销毁已存在的实例
    let myChart = echarts.getInstanceByDom(chartDom);
    if (myChart) {
        myChart.dispose();
    }

    // 重新初始化
    myChart = echarts.init(chartDom);

    // 获取布局类型
    const layoutType = document.getElementById('relation-layout-type')?.value || 'force';

    const option = {
        title: {
            text: title,
            left: 'center',
            top: 10
        },
        tooltip: {
            formatter: function(params) {
                if (params.dataType === 'node') {
                    return `${params.data.name}<br/>节点ID: ${params.data.id}`;
                } else if (params.dataType === 'edge') {
                    const edgeLabel = params.data.label?.formatter || '';
                    return `${params.data.source} → ${params.data.target}<br/>关系类型: ${edgeLabel}<br/>关系强度: ${params.data.value.toFixed(2)}`;
                }
            }
        },
        series: [{
            type: 'graph',
            layout: layoutType,
            data: nodes,
            links: links,
            roam: true,
            label: {
                show: true,
                position: 'right',
                formatter: '{b}'
            },
            labelLayout: {
                hideOverlap: true
            },
            edgeLabel: {
                show: filteredUserId ? true : false,  // 筛选模式下显示边标签
                fontSize: 10
            },
            scaleLimit: {
                min: 0.4,
                max: 2
            },
            lineStyle: {
                color: 'source',
                curveness: 0.3
            },
            force: layoutType === 'force' ? {
                repulsion: filteredUserId ? 150 : 200,
                edgeLength: filteredUserId ? [80, 200] : [50, 150],
                gravity: 0.1
            } : undefined,
            circular: layoutType === 'circular' ? {
                rotateLabel: true
            } : undefined
        }]
    };

    myChart.setOption(option);

    // 移除旧的resize监听器
    if (relationshipChartResizeHandler) {
        window.removeEventListener('resize', relationshipChartResizeHandler);
    }

    // 创建新的resize监听器
    relationshipChartResizeHandler = () => myChart.resize();
    window.addEventListener('resize', relationshipChartResizeHandler);

    // 存储实例引用
    relationshipChartInstance = myChart;
}

/**
 * 根据消息数量获取节点颜色
 */
function getNodeColor(messageCount) {
    if (messageCount > 100) return '#ff4757';
    if (messageCount > 50) return '#ff6348';
    if (messageCount > 20) return '#ffa502';
    if (messageCount > 10) return '#1e90ff';
    return '#70a1ff';
}

/**
 * 渲染成员列表
 */
function renderMembersList(data) {
    const container = document.getElementById('members-list');
    if (!container) return;

    const members = data.members || [];
    const relations = data.relations || [];

    if (members.length === 0) {
        container.innerHTML = '<div class="empty-message">暂无成员数据</div>';
        return;
    }

    // 计算每个成员的关系数
    const relationCounts = {};
    relations.forEach(rel => {
        relationCounts[rel.source] = (relationCounts[rel.source] || 0) + 1;
        relationCounts[rel.target] = (relationCounts[rel.target] || 0) + 1;
    });

    // 按消息数量排序
    const sortedMembers = [...members].sort((a, b) =>
        (b.message_count || 0) - (a.message_count || 0)
    );

    let html = '<div class="members-table">';
    html += `
        <div class="member-row member-header">
            <div class="member-col">昵称</div>
            <div class="member-col">用户ID</div>
            <div class="member-col">消息数</div>
            <div class="member-col">关系数</div>
            <div class="member-col">活跃度</div>
        </div>
    `;

    sortedMembers.forEach(member => {
        const relationCount = relationCounts[member.user_id] || 0;
        const messageCount = member.message_count || 0;
        const activityLevel = getActivityLevel(messageCount);

        html += `
            <div class="member-row" data-user-id="${member.user_id}" data-nickname="${escapeHtml(member.nickname || '')}">
                <div class="member-col">
                    <div class="member-avatar">
                        <i class="material-icons">person</i>
                    </div>
                    <span>${escapeHtml(member.nickname || member.user_id)}</span>
                </div>
                <div class="member-col">${member.user_id}</div>
                <div class="member-col">${messageCount}</div>
                <div class="member-col">${relationCount}</div>
                <div class="member-col">
                    <span class="activity-badge activity-${activityLevel}">${activityLevel}</span>
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

/**
 * 获取活跃度等级
 */
function getActivityLevel(messageCount) {
    if (messageCount > 100) return 'high';
    if (messageCount > 20) return 'medium';
    return 'low';
}

/**
 * 筛选成员列表
 */
function filterMembersList() {
    const searchInput = document.getElementById('memberSearchInput');
    if (!searchInput) return;

    const searchTerm = searchInput.value.toLowerCase();
    const memberRows = document.querySelectorAll('.member-row:not(.member-header)');

    memberRows.forEach(row => {
        const nickname = row.getAttribute('data-nickname')?.toLowerCase() || '';
        const userId = row.getAttribute('data-user-id')?.toLowerCase() || '';

        if (nickname.includes(searchTerm) || userId.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

/**
 * 更新关系图谱（切换布局时调用）
 */
function updateRelationshipChart() {
    if (currentGroupRelations) {
        renderRelationshipChart(currentGroupRelations);
    }
}

/**
 * 返回群组列表
 */
function backToGroupList() {
    // 取消任何正在进行的请求
    if (loadGroupRelationsController) {
        loadGroupRelationsController.abort();
        loadGroupRelationsController = null;
    }

    // 销毁ECharts实例，避免内存泄漏
    const chartContainer = document.getElementById('relationship-graph-chart');
    if (chartContainer) {
        const existingChart = echarts.getInstanceByDom(chartContainer);
        if (existingChart) {
            existingChart.dispose();
        }
    }

    // 移除resize监听器
    if (relationshipChartResizeHandler) {
        window.removeEventListener('resize', relationshipChartResizeHandler);
        relationshipChartResizeHandler = null;
    }

    // 清除图表实例引用
    relationshipChartInstance = null;

    // 切换显示 - 添加null检查
    const groupListSection = document.querySelector('.group-list-section');
    const relationshipDetail = document.getElementById('relationship-detail');

    if (groupListSection) groupListSection.style.display = 'block';
    if (relationshipDetail) relationshipDetail.style.display = 'none';

    currentGroupRelations = null;
    currentGroupId = null;
    filteredUserId = null;  // 清除筛选状态
}

/**
 * HTML转义函数
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 页面加载完成后初始化选项卡
document.addEventListener('DOMContentLoaded', function() {
    // 等待DOM完全加载后再初始化
    setTimeout(() => {
        if (document.querySelector('.tab-btn')) {
            initializeReviewTabs();
        }

        // 检查是否在社交关系页面，如果是则加载群组列表
        const socialRelationsPage = document.getElementById('social-relations-page');
        if (socialRelationsPage && socialRelationsPage.classList.contains('active')) {
            loadGroupList();
        }
    }, 100);
});

// ==================== Three.js 加载检查 ====================
window.addEventListener('load', () => {
    console.log('🔍 检查 Three.js 加载状态...');
    console.log('THREE 存在:', typeof THREE !== 'undefined');
    if (typeof THREE !== 'undefined') {
        console.log('THREE 版本:', THREE.REVISION);
        console.log('OrbitControls 存在:', typeof THREE.OrbitControls !== 'undefined');
    }
    console.log('SocialGraph3D 存在:', typeof window.SocialGraph3D !== 'undefined');
});

// ==================== 3D社交关系图谱集成 ====================

// 全局变量
let socialGraph3D = null;  // 3D图谱实例
let currentGraphMode = '2d';  // 当前图谱模式：2d 或 3d
let currentRelationsData = null;  // 当前的关系数据（用于2D/3D切换）

/**
 * 切换图谱模式 (2D/3D)
 */
function switchGraphMode(mode) {
    console.log(`🔄 切换图谱模式: ${currentGraphMode} -> ${mode}`);

    if (mode === currentGraphMode) {
        console.log('⚠️ 模式相同，跳过切换');
        return;
    }

    currentGraphMode = mode;

    // 更新按钮状态
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        if (btn.dataset.mode === mode) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // 更新body类名以控制CSS显示/隐藏
    if (mode === '3d') {
        document.body.classList.add('graph-3d-mode');
    } else {
        document.body.classList.remove('graph-3d-mode');
    }

    // 显示/隐藏相应的容器
    const chart2D = document.getElementById('relationship-graph-chart');
    const chart3D = document.getElementById('relationship-graph-3d');

    console.log('📦 DOM元素检查:', {
        chart2D: !!chart2D,
        chart3D: !!chart3D
    });

    if (mode === '3d') {
        // 切换到3D模式
        console.log('✅ 切换到3D模式');
        if (chart2D) chart2D.style.display = 'none';
        if (chart3D) chart3D.style.display = 'block';

        // 初始化3D图谱
        init3DGraph();

        // 如果有当前数据，加载到3D图谱
        if (currentRelationsData) {
            console.log('📊 加载数据到3D图谱:', currentRelationsData);
            load3DGraphData(currentRelationsData);
        } else {
            console.warn('⚠️ 没有可用的关系数据');
        }
    } else {
        // 切换到2D模式
        console.log('✅ 切换到2D模式');
        if (chart2D) chart2D.style.display = 'block';
        if (chart3D) chart3D.style.display = 'none';

        // 销毁3D图谱
        if (socialGraph3D) {
            socialGraph3D.destroy();
            socialGraph3D = null;
        }

        // 如果有当前数据，重新渲染2D图谱
        if (currentRelationsData) {
            updateRelationshipChart();
        }
    }
}

/**
 * 初始化3D图谱
 */
function init3DGraph() {
    console.log('🔧 初始化3D图谱...');

    if (!window.SocialGraph3D) {
        console.error('❌ SocialGraph3D class not found. Make sure social_graph_3d.js is loaded.');
        console.log('可用的全局对象:', Object.keys(window).filter(k => k.includes('Social') || k.includes('THREE')));
        return;
    }

    console.log('✅ SocialGraph3D 类已找到');

    // 如果已存在，先销毁
    if (socialGraph3D) {
        console.log('⚠️ 销毁旧的3D图谱实例');
        socialGraph3D.destroy();
    }

    // 检查容器是否存在
    const container = document.getElementById('relationship-graph-3d');
    if (!container) {
        console.error('❌ 容器 relationship-graph-3d 不存在');
        return;
    }

    console.log('✅ 容器已找到:', container);

    // 创建新实例
    try {
        socialGraph3D = new SocialGraph3D('relationship-graph-3d');
        console.log('✅ SocialGraph3D 实例创建成功:', socialGraph3D);
    } catch (error) {
        console.error('❌ 创建 SocialGraph3D 实例失败:', error);
        return;
    }

    // 监听节点选中事件
    container.addEventListener('nodeSelected', (event) => {
        const nodeData = event.detail;
        console.log('🎯 Selected node in 3D:', nodeData);

        // 可以在这里更新成员详细信息
        // TODO: 高亮选中的成员
    });

    console.log('✅ 3D图谱初始化完成');
}

/**
 * 加载数据到3D图谱
 */
function load3DGraphData(data) {
    console.log('📥 load3DGraphData 被调用，数据:', data);

    if (!socialGraph3D) {
        console.log('⚠️ socialGraph3D 不存在，尝试初始化...');
        init3DGraph();
    }

    if (!socialGraph3D) {
        console.error('❌ 初始化3D图谱失败');
        return;
    }

    if (!data || !data.nodes || !data.links) {
        console.error('❌ 数据格式错误:', data);
        return;
    }

    console.log(`📊 原始数据: ${data.nodes.length} 个节点, ${data.links.length} 条边`);

    // 转换数据格式为3D图谱需要的格式
    const nodes = data.nodes.map(node => ({
        id: node.id || node.name,
        label: node.name || node.id,
        strength: node.symbolSize || 10
    }));

    const edges = data.links.map(link => ({
        source: link.source,
        target: link.target,
        strength: link.value || 1
    }));

    console.log(`✅ 转换后数据: ${nodes.length} 个节点, ${edges.length} 条边`);
    console.log('节点示例:', nodes[0]);
    console.log('边示例:', edges[0]);

    // 加载数据
    try {
        socialGraph3D.loadData(nodes, edges);
        console.log('✅ 数据已加载到3D图谱');
    } catch (error) {
        console.error('❌ 加载数据到3D图谱失败:', error);
    }
}

/**
 * 更改3D主题
 */
function change3DTheme(themeName) {
    console.log(`🎨 change3DTheme 被调用: ${themeName}`);

    if (socialGraph3D) {
        socialGraph3D.setTheme(themeName);
        console.log('✅ 主题已设置');
    } else {
        console.error('❌ socialGraph3D 不存在');
    }
}

/**
 * 重置3D相机位置
 */
function resetGraph3DCamera() {
    if (socialGraph3D) {
        socialGraph3D.resetCamera();
    }
}

/**
 * 修改原有的loadGroupRelations函数，保存数据以支持2D/3D切换
 * 注意：这需要修改现有的loadGroupRelations函数，在渲染图表后保存数据
 */
// 在现有的updateRelationshipChart函数后添加数据保存
const originalUpdateRelationshipChart = window.updateRelationshipChart;
if (originalUpdateRelationshipChart && typeof originalUpdateRelationshipChart === 'function') {
    window.updateRelationshipChart = function() {
        // 调用原函数
        originalUpdateRelationshipChart();

        // 保存当前数据（从ECharts实例中获取）
        const chartDom = document.getElementById('relationship-graph-chart');
        if (chartDom && window.echarts) {
            const chartInstance = window.echarts.getInstanceByDom(chartDom);
            if (chartInstance) {
                const option = chartInstance.getOption();
                if (option && option.series && option.series[0]) {
                    currentRelationsData = {
                        nodes: option.series[0].data || [],
                        links: option.series[0].links || []
                    };

                    // 如果当前是3D模式，更新3D图谱
                    if (currentGraphMode === '3d' && socialGraph3D) {
                        load3DGraphData(currentRelationsData);
                    }
                }
            }
        }
    };
}

console.log('✅ 3D社交关系图谱集成完成');

// ========== 黑话学习系统 ==========

/**
 * 刷新黑话学习页面
 */
async function refreshJargonPage() {
    await loadJargonGroups();
    await loadJargonStats();
    await loadJargonList();
}

/**
 * 加载黑话群组列表
 */
async function loadJargonGroups() {
    try {
        const response = await fetch('/api/jargon/groups');
        const result = await response.json();

        if (result.success && result.data) {
            const groupFilter = document.getElementById('jargon-group-filter');
            if (groupFilter) {
                // 保留第一个选项（全部群组）
                groupFilter.innerHTML = '<option value="">全部群组</option>';

                // 添加群组选项
                result.data.forEach(group => {
                    const option = document.createElement('option');
                    option.value = group.group_id;
                    option.textContent = `${group.group_id} (${group.confirmed_jargon}个黑话)`;
                    groupFilter.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('加载黑话群组列表失败:', error);
    }
}

/**
 * 加载黑话统计信息
 */
async function loadJargonStats(groupId = null) {
    try {
        let url = '/api/jargon/stats';
        if (groupId) {
            url += `?group_id=${encodeURIComponent(groupId)}`;
        }

        const response = await fetch(url);
        const result = await response.json();

        if (result.success && result.data) {
            const stats = result.data;

            // 更新统计卡片
            const totalCandidates = document.getElementById('jargon-total-candidates');
            if (totalCandidates) totalCandidates.textContent = stats.total_candidates || 0;

            const confirmed = document.getElementById('jargon-confirmed');
            if (confirmed) confirmed.textContent = stats.confirmed_jargon || 0;

            const completed = document.getElementById('jargon-completed');
            if (completed) completed.textContent = stats.completed_inference || 0;

            const totalOccurrences = document.getElementById('jargon-total-occurrences');
            if (totalOccurrences) totalOccurrences.textContent = stats.total_occurrences || 0;
        }
    } catch (error) {
        console.error('加载黑话统计信息失败:', error);
    }
}

/**
 * 加载黑话列表
 */
async function loadJargonList() {
    const groupFilter = document.getElementById('jargon-group-filter');
    const statusFilter = document.getElementById('jargon-status-filter');

    const groupId = groupFilter ? groupFilter.value : '';
    const onlyConfirmed = statusFilter ? statusFilter.value : 'true';

    try {
        let url = `/api/jargon/list?only_confirmed=${onlyConfirmed}&limit=100`;
        if (groupId) {
            url += `&group_id=${encodeURIComponent(groupId)}`;
        }

        const response = await fetch(url);
        const result = await response.json();

        const listContainer = document.getElementById('jargon-list');
        if (!listContainer) return;

        if (result.success && result.data && result.data.length > 0) {
            listContainer.innerHTML = result.data.map(jargon => `
                <div class="jargon-item ${jargon.is_complete ? 'complete' : ''}" data-id="${jargon.id}">
                    <div class="jargon-content">
                        <span class="jargon-word">${escapeHtml(jargon.content)}</span>
                        <span class="jargon-badge ${jargon.is_jargon ? 'confirmed' : 'pending'}">
                            ${jargon.is_jargon ? '已确认' : '待验证'}
                        </span>
                        ${jargon.is_complete ? '<span class="jargon-badge complete">推断完成</span>' : ''}
                    </div>
                    <div class="jargon-meaning">
                        ${jargon.meaning ? escapeHtml(jargon.meaning) : '<em>暂无含义</em>'}
                    </div>
                    <div class="jargon-meta">
                        <span class="jargon-count">出现 ${jargon.count} 次</span>
                        <span class="jargon-group">群组: ${escapeHtml(jargon.chat_id || '未知')}</span>
                        <span class="jargon-time">${jargon.updated_at ? formatDateTime(jargon.updated_at) : ''}</span>
                    </div>
                    <div class="jargon-actions">
                        <button class="btn btn-sm btn-secondary" onclick="toggleJargonGlobal(${jargon.id})" title="设为/取消全局黑话">
                            <i class="material-icons">public</i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteJargon(${jargon.id})" title="删除">
                            <i class="material-icons">delete</i>
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            listContainer.innerHTML = '<div class="empty-message">暂无黑话学习记录</div>';
        }

        // 更新统计
        await loadJargonStats(groupId);
    } catch (error) {
        console.error('加载黑话列表失败:', error);
        const listContainer = document.getElementById('jargon-list');
        if (listContainer) {
            listContainer.innerHTML = '<div class="error-message">加载黑话列表失败</div>';
        }
    }
}

/**
 * 搜索黑话
 */
async function searchJargon() {
    const searchInput = document.getElementById('jargon-search-input');
    const groupFilter = document.getElementById('jargon-group-filter');

    const keyword = searchInput ? searchInput.value.trim() : '';
    const groupId = groupFilter ? groupFilter.value : '';

    if (!keyword) {
        await loadJargonList();
        return;
    }

    try {
        let url = `/api/jargon/search?keyword=${encodeURIComponent(keyword)}&limit=50`;
        if (groupId) {
            url += `&group_id=${encodeURIComponent(groupId)}`;
        }

        const response = await fetch(url);
        const result = await response.json();

        const listContainer = document.getElementById('jargon-list');
        if (!listContainer) return;

        if (result.success && result.data && result.data.length > 0) {
            listContainer.innerHTML = result.data.map(jargon => `
                <div class="jargon-item ${jargon.is_complete ? 'complete' : ''}" data-id="${jargon.id}">
                    <div class="jargon-content">
                        <span class="jargon-word">${escapeHtml(jargon.content)}</span>
                        <span class="jargon-badge ${jargon.is_jargon ? 'confirmed' : 'pending'}">
                            ${jargon.is_jargon ? '已确认' : '待验证'}
                        </span>
                        ${jargon.is_complete ? '<span class="jargon-badge complete">推断完成</span>' : ''}
                    </div>
                    <div class="jargon-meaning">
                        ${jargon.meaning ? escapeHtml(jargon.meaning) : '<em>暂无含义</em>'}
                    </div>
                    <div class="jargon-meta">
                        <span class="jargon-count">出现 ${jargon.count} 次</span>
                    </div>
                    <div class="jargon-actions">
                        <button class="btn btn-sm btn-secondary" onclick="toggleJargonGlobal(${jargon.id})" title="设为/取消全局黑话">
                            <i class="material-icons">public</i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteJargon(${jargon.id})" title="删除">
                            <i class="material-icons">delete</i>
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            listContainer.innerHTML = `<div class="empty-message">未找到包含 "${escapeHtml(keyword)}" 的黑话</div>`;
        }
    } catch (error) {
        console.error('搜索黑话失败:', error);
    }
}

/**
 * 删除黑话
 */
async function deleteJargon(jargonId) {
    if (!confirm('确定要删除这条黑话记录吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/jargon/${jargonId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            showToast('黑话记录已删除', 'success');
            await loadJargonList();
        } else {
            showToast(result.error || '删除失败', 'error');
        }
    } catch (error) {
        console.error('删除黑话失败:', error);
        showToast('删除黑话失败', 'error');
    }
}

/**
 * 切换黑话的全局状态
 */
async function toggleJargonGlobal(jargonId) {
    try {
        const response = await fetch(`/api/jargon/${jargonId}/toggle_global`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showToast(result.message, 'success');
            await loadJargonList();
        } else {
            showToast(result.error || '操作失败', 'error');
        }
    } catch (error) {
        console.error('切换黑话全局状态失败:', error);
        showToast('操作失败', 'error');
    }
}

/**
 * 切换全局黑话面板显示/隐藏
 */
async function toggleGlobalJargonPanel() {
    const panel = document.getElementById('global-jargon-panel');
    const toggleText = document.getElementById('global-panel-toggle-text');

    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        toggleText.textContent = '收起';
        await loadGlobalJargonList();
    } else {
        panel.style.display = 'none';
        toggleText.textContent = '展开';
    }
}

/**
 * 加载全局共享黑话列表
 */
async function loadGlobalJargonList() {
    try {
        const response = await fetch('/api/jargon/global?limit=50');
        const result = await response.json();

        const listContainer = document.getElementById('global-jargon-list');
        const countElement = document.getElementById('global-jargon-count');

        if (result.success && result.data) {
            countElement.textContent = result.total || 0;

            if (result.data.length === 0) {
                listContainer.innerHTML = '<div class="empty-message">暂无全局共享的黑话</div>';
                return;
            }

            listContainer.innerHTML = result.data.map(item => `
                <div class="jargon-item compact">
                    <div class="jargon-main">
                        <span class="jargon-content">${escapeHtml(item.content)}</span>
                        <span class="jargon-meaning">${escapeHtml(item.meaning || '含义待推断')}</span>
                    </div>
                    <div class="jargon-meta">
                        <span class="jargon-count" title="出现次数">
                            <i class="material-icons">repeat</i> ${item.count}
                        </span>
                        <span class="jargon-source" title="来源群组">
                            <i class="material-icons">group</i> ${item.chat_id}
                        </span>
                        <button class="btn btn-danger btn-tiny" onclick="removeFromGlobal(${item.id})" title="取消全局共享">
                            <i class="material-icons">remove_circle</i>
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            listContainer.innerHTML = '<div class="error-message">加载失败</div>';
        }
    } catch (error) {
        console.error('加载全局黑话列表失败:', error);
        document.getElementById('global-jargon-list').innerHTML = '<div class="error-message">加载失败</div>';
    }
}

/**
 * 从全局共享中移除黑话
 */
async function removeFromGlobal(jargonId) {
    try {
        const response = await fetch(`/api/jargon/${jargonId}/set_global`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_global: false })
        });

        const result = await response.json();

        if (result.success) {
            showToast('已取消全局共享', 'success');
            await loadGlobalJargonList();
            await loadJargonList();
        } else {
            showToast(result.error || '操作失败', 'error');
        }
    } catch (error) {
        console.error('取消全局共享失败:', error);
        showToast('操作失败', 'error');
    }
}

/**
 * 设置黑话为全局共享
 */
async function setJargonGlobal(jargonId) {
    try {
        const response = await fetch(`/api/jargon/${jargonId}/set_global`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_global: true })
        });

        const result = await response.json();

        if (result.success) {
            showToast('已设为全局共享', 'success');
            await loadJargonList();
            // 如果全局面板已展开，刷新它
            const panel = document.getElementById('global-jargon-panel');
            if (panel.style.display !== 'none') {
                await loadGlobalJargonList();
            }
        } else {
            showToast(result.error || '操作失败', 'error');
        }
    } catch (error) {
        console.error('设置全局共享失败:', error);
        showToast('操作失败', 'error');
    }
}

/**
 * 显示同步对话框
 */
function showSyncDialog() {
    // 创建模态框
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'sync-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="material-icons">sync</i> 同步全局黑话到群组</h3>
                <button class="modal-close" onclick="closeSyncDialog()">
                    <i class="material-icons">close</i>
                </button>
            </div>
            <div class="modal-body">
                <p>选择要同步全局黑话的目标群组：</p>
                <select id="sync-target-group" class="form-control">
                    <option value="">-- 请选择群组 --</option>
                </select>
                <p class="hint">同步后，全局共享的黑话将复制到目标群组（已存在的不会重复添加）。</p>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeSyncDialog()">取消</button>
                <button class="btn btn-primary" onclick="executeSyncToGroup()">
                    <i class="material-icons">sync</i>
                    开始同步
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // 加载群组列表
    loadSyncTargetGroups();
}

/**
 * 加载同步目标群组列表
 */
async function loadSyncTargetGroups() {
    try {
        const response = await fetch('/api/jargon/groups');
        const result = await response.json();

        const select = document.getElementById('sync-target-group');
        if (result.success && result.data) {
            result.data.forEach(group => {
                const option = document.createElement('option');
                option.value = group.group_id;
                option.textContent = `${group.group_id} (${group.confirmed_jargon} 条黑话)`;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载群组列表失败:', error);
    }
}

/**
 * 执行同步到群组
 */
async function executeSyncToGroup() {
    const targetGroup = document.getElementById('sync-target-group').value;

    if (!targetGroup) {
        showToast('请选择目标群组', 'error');
        return;
    }

    try {
        const response = await fetch('/api/jargon/sync_to_group', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_group_id: targetGroup })
        });

        const result = await response.json();

        if (result.success) {
            showToast(result.message, 'success');
            closeSyncDialog();
            await loadJargonList();
        } else {
            showToast(result.error || '同步失败', 'error');
        }
    } catch (error) {
        console.error('同步失败:', error);
        showToast('同步失败', 'error');
    }
}

/**
 * 关闭同步对话框
 */
function closeSyncDialog() {
    const modal = document.getElementById('sync-modal');
    if (modal) {
        modal.remove();
    }
}

/**
 * HTML转义函数
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 格式化日期时间
 */
function formatDateTime(dateStr) {
    if (!dateStr) return '';
    try {
        const date = new Date(dateStr);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateStr;
    }
}

function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    const formatted = value >= 10 || unitIndex === 0 ? Math.round(value) : value.toFixed(1);
    return `${formatted}${units[unitIndex]}`;
}

/**
 * 显示Toast提示
 */
function showToast(message, type = 'info') {
    // 创建toast元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // 添加样式
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 24px;
        border-radius: 4px;
        color: white;
        font-size: 14px;
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s ease;
        background-color: ${type === 'success' ? '#4caf50' : type === 'error' ? '#f44336' : '#2196f3'};
    `;

    document.body.appendChild(toast);

    // 显示动画
    setTimeout(() => {
        toast.style.opacity = '1';
    }, 10);

    // 自动隐藏
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

/**
 * 初始化 Bug 自助提交悬浮窗
 */
function initBugAssistantWidget() {
    const wrapper = document.querySelector('.bug-assistant-wrapper');
    const panel = document.getElementById('bugAssistantPanel');
    const fab = document.getElementById('bugAssistantFab');
    const closeBtn = document.getElementById('bugAssistantClose');
    const form = document.getElementById('bugAssistantForm');
    const attachmentInput = document.getElementById('bugAttachmentInput');
    const clearAttachmentsBtn = document.getElementById('bugClearAttachments');
    const resetFormBtn = document.getElementById('bugResetForm');

    if (!wrapper || !panel || !fab) {
        return;
    }

    const dragState = {
        isDragging: false,
        moved: false,
        pointerId: null
    };

    const positionPanel = () => {
        if (!panel.classList.contains('open')) {
            return;
        }

        const fabRect = fab.getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const padding = 16;

        const preferLeft = fabRect.left + fabRect.width / 2 > viewportWidth / 2;
        const preferTop = fabRect.top + fabRect.height / 2 > viewportHeight / 2;

        let left = preferLeft ? fabRect.right - panelRect.width : fabRect.left;
        let top = preferTop ? fabRect.top - panelRect.height - padding : fabRect.bottom + padding;

        left = clamp(left, padding, viewportWidth - panelRect.width - padding);
        top = clamp(top, padding, viewportHeight - panelRect.height - padding);

        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
    };

    const togglePanel = (shouldOpen) => {
        if (shouldOpen) {
            panel.classList.add('open');
            panel.setAttribute('aria-hidden', 'false');
            fab.setAttribute('aria-expanded', 'true');
            positionPanel();
            if (!bugAssistantState.config) {
                loadBugAssistantConfig();
            }
        } else {
            panel.classList.remove('open');
            panel.setAttribute('aria-hidden', 'true');
            fab.setAttribute('aria-expanded', 'false');
        }
    };

    initBugAssistantDrag({
        wrapper,
        fab,
        panel,
        dragState,
        onPositionChange: positionPanel
    });

    fab.addEventListener('click', (event) => {
        if (dragState.moved) {
            dragState.moved = false;
            return;
        }
        event.stopPropagation();
        togglePanel(!panel.classList.contains('open'));
    });

    closeBtn?.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        togglePanel(false);
    });

    document.addEventListener('click', (event) => {
        if (!panel.contains(event.target) && event.target !== fab && panel.classList.contains('open')) {
            togglePanel(false);
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && panel.classList.contains('open')) {
            togglePanel(false);
            fab.focus();
        }
    });

    window.addEventListener('resize', () => {
        positionPanel();
    });

    panel.addEventListener('paste', (event) => {
        handleBugAttachmentPaste(event, panel);
    });

    form?.addEventListener('submit', submitBugAssistantForm);
    attachmentInput?.addEventListener('change', handleBugAttachmentInput);
    clearAttachmentsBtn?.addEventListener('click', clearBugAttachments);
    resetFormBtn?.addEventListener('click', () => clearBugAssistantForm());

    loadBugAssistantConfig();
}

async function loadBugAssistantConfig() {
    const statusCard = document.getElementById('bugAssistantStatusCard');
    if (statusCard) {
        statusCard.querySelector('.status-title').textContent = '初始化Bug助手';
        statusCard.querySelector('.status-desc').textContent = '正在连接服务器...';
        statusCard.querySelector('.status-hint').textContent = '请稍候';
    }

    try {
        const response = await fetch('/api/bug_report/config');
        if (!response.ok) {
            throw new Error(await response.text());
        }
        bugAssistantState.config = await response.json();
        bugAssistantState.formInitialized = false;
        updateBugAssistantUI();
    } catch (error) {
        console.error('获取Bug助手配置失败:', error);
        bugAssistantState.config = {
            enabled: false,
            message: '无法连接到Bug接口，请稍后再试'
        };
        updateBugAssistantUI(true);
    }
}

function updateBugAssistantUI(hasError = false) {
    const statusCard = document.getElementById('bugAssistantStatusCard');
    const form = document.getElementById('bugAssistantForm');
    const submitBtn = document.getElementById('bugAssistantSubmit');
    const attachmentInput = document.getElementById('bugAttachmentInput');
    const clearBtn = document.getElementById('bugClearAttachments');
    const resetBtn = document.getElementById('bugResetForm');
    const includeLogs = document.getElementById('bugIncludeLogs');

    if (!statusCard || !form) {
        return;
    }

    const enabled = bugAssistantState.config?.enabled && !hasError;

    if (enabled) {
        statusCard.querySelector('.status-title').textContent = '服务器已连接';
        statusCard.querySelector('.status-desc').textContent = bugAssistantState.config.message || '可直接上传截图并附带日志';
        statusCard.querySelector('.status-hint').textContent = `Bug自助提交助手运行中，最多支持 ${bugAssistantState.config.maxImages || BUG_DEFAULT_MAX_IMAGES} 张附件`;
    } else {
        statusCard.querySelector('.status-title').textContent = 'Bug助手不可用';
        statusCard.querySelector('.status-desc').textContent = bugAssistantState.config?.message || '请联系管理员检查接口配置';
        statusCard.querySelector('.status-hint').textContent = '仍可通过其他渠道反馈问题';
    }

    form.classList.toggle('disabled', !enabled || bugAssistantState.submitting);
    const controllableElements = form.querySelectorAll('input, textarea, select, button');
    controllableElements.forEach((element) => {
        element.disabled = !enabled || bugAssistantState.submitting;
    });

    if (!enabled) {
        return;
    }

    populateBugAssistantSelect('bugSeverity', bugAssistantState.config.severityOptions);
    populateBugAssistantSelect('bugPriority', bugAssistantState.config.priorityOptions);
    populateBugAssistantSelect('bugType', bugAssistantState.config.typeOptions);

    if (!bugAssistantState.formInitialized) {
        document.getElementById('bugAssistantTitle').value = '';
        document.getElementById('bugSteps').value = '';
        document.getElementById('bugDescription').value = '';
        document.getElementById('bugEnvironment').value = '';
        document.getElementById('bugBuild').value = bugAssistantState.config.defaultBuild || '';
        includeLogs.checked = true;
        bugAssistantState.uploadedFiles = [];
        bugAssistantState.pastedFiles = [];
        bugAssistantState.formInitialized = true;
    }

    renderBugAttachmentList();
    renderBugLogPreview(bugAssistantState.config.logPreview);
    submitBtn.textContent = bugAssistantState.submitting ? '提交中...' : '提交到服务器';
    if (attachmentInput) attachmentInput.value = '';
    if (clearBtn) clearBtn.disabled = bugAssistantState.submitting;
    if (resetBtn) resetBtn.disabled = bugAssistantState.submitting;
}

function populateBugAssistantSelect(selectId, options = []) {
    const select = document.getElementById(selectId);
    if (!select || !options.length) {
        return;
    }
    select.innerHTML = options.map((option) => `<option value="${option.value}">${option.label}</option>`).join('');
}

function renderBugLogPreview(previewList = []) {
    const container = document.getElementById('bugLogPreview');
    if (!container) {
        return;
    }

    if (!previewList || !previewList.length) {
        container.innerHTML = '<p class="muted-text">未找到可附带的日志。可以在运行目录下创建 astrbot.log。</p>';
        return;
    }

    const cards = previewList.map((log) => {
        const safePreview = escapeHtml(log.preview || '').slice(-1200);
        return `
            <div class="log-card">
                <h5>${log.path}（${formatBytes(log.size)}）</h5>
                <pre>${safePreview}</pre>
            </div>
        `;
    });

    container.innerHTML = cards.join('');
}

function handleBugAttachmentInput(event) {
    if (!bugAssistantState.config?.enabled) {
        return;
    }
    const files = Array.from(event.target.files || []);
    const maxImages = bugAssistantState.config.maxImages || BUG_DEFAULT_MAX_IMAGES;
    const maxBytes = bugAssistantState.config.maxImageBytes || BUG_DEFAULT_MAX_IMAGE_BYTES;
    const existingCount = bugAssistantState.pastedFiles.length;
    const availableSlots = Math.max(maxImages - existingCount, 0);

    if (!availableSlots) {
        showToast('附件数量已达上限', 'error');
        event.target.value = '';
        return;
    }

    const sanitized = [];
    for (const file of files.slice(0, availableSlots)) {
        if (file.size > maxBytes) {
            showToast(`附件 ${file.name} 超过大小限制`, 'error');
            continue;
        }
        sanitized.push(file);
    }

    bugAssistantState.uploadedFiles = sanitized;
    renderBugAttachmentList();
}

function handleBugAttachmentPaste(event, panel) {
    if (!panel.classList.contains('open') || !bugAssistantState.config?.enabled) {
        return;
    }
    const clipboardItems = event.clipboardData?.items || [];
    const maxImages = bugAssistantState.config.maxImages || BUG_DEFAULT_MAX_IMAGES;
    const maxBytes = bugAssistantState.config.maxImageBytes || BUG_DEFAULT_MAX_IMAGE_BYTES;
    let added = false;

    for (const item of clipboardItems) {
        if (item.kind !== 'file' || !item.type.startsWith('image/')) {
            continue;
        }
        const file = item.getAsFile();
        if (!file) continue;

        const totalCount = bugAssistantState.uploadedFiles.length + bugAssistantState.pastedFiles.length;
        if (totalCount >= maxImages) {
            showToast('附件数量已达上限', 'error');
            break;
        }
        if (file.size > maxBytes) {
            showToast('粘贴的图片超过大小限制', 'error');
            continue;
        }
        bugAssistantState.pastedFiles.push(file);
        added = true;
    }

    if (added) {
        event.preventDefault();
        renderBugAttachmentList();
        showToast('已添加粘贴的截图', 'success');
    }
}

function renderBugAttachmentList() {
    const container = document.getElementById('bugAttachmentList');
    if (!container) return;

    const allFiles = [
        ...bugAssistantState.uploadedFiles.map((file, index) => ({ file, index, type: 'upload' })),
        ...bugAssistantState.pastedFiles.map((file, index) => ({ file, index, type: 'paste' }))
    ];

    if (!allFiles.length) {
        container.innerHTML = '<p class="muted-text">当前没有附件。</p>';
        return;
    }

    const chips = allFiles.map((item) => `
        <div class="attachment-chip">
            <span class="material-icons" aria-hidden="true">insert_photo</span>
            <span>${item.file.name || (item.type === 'paste' ? '粘贴截图' : '附件')}</span>
            <span class="muted-text">${formatBytes(item.file.size)}</span>
            <button type="button" aria-label="移除附件" onclick="removeBugAttachment('${item.type}', ${item.index})">
                <span class="material-icons">close</span>
            </button>
        </div>
    `);

    container.innerHTML = chips.join('');
}

function removeBugAttachment(type, index) {
    if (type === 'upload') {
        bugAssistantState.uploadedFiles.splice(index, 1);
        const input = document.getElementById('bugAttachmentInput');
        if (input) input.value = '';
    } else {
        bugAssistantState.pastedFiles.splice(index, 1);
    }
    renderBugAttachmentList();
}

function clearBugAttachments() {
    bugAssistantState.uploadedFiles = [];
    bugAssistantState.pastedFiles = [];
    const input = document.getElementById('bugAttachmentInput');
    if (input) input.value = '';
    renderBugAttachmentList();
}

function clearBugAssistantForm(resetDefaults = false) {
    const form = document.getElementById('bugAssistantForm');
    if (!form) return;

    form.reset();
    bugAssistantState.uploadedFiles = [];
    bugAssistantState.pastedFiles = [];

    if (resetDefaults && bugAssistantState.config) {
        document.getElementById('bugBuild').value = bugAssistantState.config.defaultBuild || '';
        document.getElementById('bugIncludeLogs').checked = true;
    }

    renderBugAttachmentList();
}

async function submitBugAssistantForm(event) {
    event.preventDefault();
    if (!bugAssistantState.config?.enabled || bugAssistantState.submitting) {
        return;
    }

    const title = document.getElementById('bugAssistantTitle').value.trim();
    const build = document.getElementById('bugBuild').value.trim();
    const steps = document.getElementById('bugSteps').value.trim();
    const description = document.getElementById('bugDescription').value.trim();
    const environment = document.getElementById('bugEnvironment').value.trim();
    const severity = document.getElementById('bugSeverity').value;
    const priority = document.getElementById('bugPriority').value;
    const bugType = document.getElementById('bugType').value;
    const includeLogs = document.getElementById('bugIncludeLogs').checked;

    if (!title) {
        showToast('请填写问题标题', 'error');
        return;
    }

    bugAssistantState.submitting = true;
    updateBugAssistantUI();

    const formData = new FormData();
    formData.append('title', title);
    formData.append('build', build || '');
    formData.append('steps', steps);
    formData.append('description', description);
    formData.append('environment', environment);
    formData.append('severity', severity);
    formData.append('priority', priority);
    formData.append('bugType', bugType);
    formData.append('includeLogs', includeLogs ? 'true' : 'false');

    [...bugAssistantState.uploadedFiles, ...bugAssistantState.pastedFiles].forEach((file, index) => {
        const safeName = file.name || `attachment_${index + 1}.png`;
        formData.append('attachments', file, safeName);
    });

    try {
        const response = await fetch('/api/bug_report', {
            method: 'POST',
            body: formData
        });

        const text = await response.text();
        let result;
        try {
            result = JSON.parse(text);
        } catch {
            result = { error: text };
        }
        if (response.ok && result.success) {
            showToast(result.message || 'Bug提交成功', 'success');
            clearBugAssistantForm(true);
        } else {
            showToast(result.error || 'Bug提交失败', 'error');
        }
    } catch (error) {
        console.error('Bug提交失败:', error);
        showToast('Bug提交失败，请检查网络后重试', 'error');
    } finally {
        bugAssistantState.submitting = false;
        updateBugAssistantUI();
    }
}

function initBugAssistantDrag({ wrapper, fab, panel, dragState, onPositionChange }) {
    if (!wrapper || !fab) {
        return;
    }

    const ensureAbsolutePosition = () => {
        if (!wrapper.dataset.dragInitialized) {
            const rect = wrapper.getBoundingClientRect();
            wrapper.style.left = `${rect.left}px`;
            wrapper.style.top = `${rect.top}px`;
            wrapper.style.right = 'auto';
            wrapper.style.bottom = 'auto';
            wrapper.dataset.dragInitialized = 'true';
        }
    };

    const handlePointerDown = (event) => {
        if (event.pointerType === 'mouse' && event.button !== 0) {
            return;
        }
        ensureAbsolutePosition();
        dragState.isDragging = true;
        dragState.moved = false;
        dragState.pointerId = event.pointerId;
        dragState.startX = event.clientX;
        dragState.startY = event.clientY;
        const rect = wrapper.getBoundingClientRect();
        dragState.startLeft = rect.left;
        dragState.startTop = rect.top;
        dragState.wrapperWidth = rect.width;
        dragState.wrapperHeight = rect.height;
        wrapper.classList.add('dragging');
        fab.setPointerCapture?.(event.pointerId);
        event.preventDefault();
    };

    const handlePointerMove = (event) => {
        if (!dragState.isDragging || (dragState.pointerId !== null && event.pointerId !== dragState.pointerId)) {
            return;
        }

        const dx = event.clientX - dragState.startX;
        const dy = event.clientY - dragState.startY;

        if (!dragState.moved && Math.hypot(dx, dy) > 4) {
            dragState.moved = true;
        }

        let newLeft = dragState.startLeft + dx;
        let newTop = dragState.startTop + dy;
        const maxLeft = window.innerWidth - dragState.wrapperWidth - 12;
        const maxTop = window.innerHeight - dragState.wrapperHeight - 12;

        newLeft = clamp(newLeft, 12, maxLeft);
        newTop = clamp(newTop, 12, maxTop);

        wrapper.style.left = `${newLeft}px`;
        wrapper.style.top = `${newTop}px`;
        wrapper.style.right = 'auto';
        wrapper.style.bottom = 'auto';

        if (panel.classList.contains('open')) {
            onPositionChange();
        }

        event.preventDefault();
    };

    const handlePointerUp = (event) => {
        if (!dragState.isDragging || (dragState.pointerId !== null && event.pointerId !== dragState.pointerId)) {
            return;
        }
        dragState.isDragging = false;
        dragState.pointerId = null;
        wrapper.classList.remove('dragging');
        fab.releasePointerCapture?.(event.pointerId);
        if (panel.classList.contains('open')) {
            onPositionChange();
        }
    };

    fab.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

// 监听搜索输入框的回车事件
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('jargon-search-input');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchJargon();
            }
        });
    }

    initBugAssistantWidget();
});

console.log('✅ 黑话学习系统集成完成');
