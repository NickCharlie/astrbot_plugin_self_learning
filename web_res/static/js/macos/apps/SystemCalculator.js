/**
 * 计算器 - 系统应用
 */
window.SystemCalculator = {
  props: { app: Object },
  data() {
    return {
      display: '0',
      currentValue: null,
      operator: null,
      waitingForOperand: false,
    };
  },
  methods: {
    inputDigit(digit) {
      if (this.waitingForOperand) {
        this.display = String(digit);
        this.waitingForOperand = false;
      } else {
        this.display = this.display === '0' ? String(digit) : this.display + digit;
      }
    },
    inputDot() {
      if (this.waitingForOperand) {
        this.display = '0.';
        this.waitingForOperand = false;
        return;
      }
      if (!this.display.includes('.')) {
        this.display += '.';
      }
    },
    clear() {
      this.display = '0';
      this.currentValue = null;
      this.operator = null;
      this.waitingForOperand = false;
    },
    toggleSign() {
      const val = parseFloat(this.display);
      this.display = String(val * -1);
    },
    inputPercent() {
      const val = parseFloat(this.display);
      this.display = String(val / 100);
    },
    performOperation(nextOp) {
      const inputValue = parseFloat(this.display);
      if (this.currentValue == null) {
        this.currentValue = inputValue;
      } else if (this.operator) {
        const result = this.calculate(this.currentValue, inputValue, this.operator);
        this.display = String(parseFloat(result.toPrecision(12)));
        this.currentValue = result;
      }
      this.waitingForOperand = true;
      this.operator = nextOp;
    },
    calculate(a, b, op) {
      switch (op) {
        case '+': return a + b;
        case '-': return a - b;
        case '*': return a * b;
        case '/': return b !== 0 ? a / b : 0;
        default: return b;
      }
    },
    equals() {
      if (this.operator && this.currentValue != null) {
        const inputValue = parseFloat(this.display);
        const result = this.calculate(this.currentValue, inputValue, this.operator);
        this.display = String(parseFloat(result.toPrecision(12)));
        this.currentValue = null;
        this.operator = null;
        this.waitingForOperand = true;
      }
    },
  },
  template: `
    <div style="width:100%;height:100%;display:flex;flex-direction:column;background:#1c1c1e;text-shadow:none;user-select:none;">
      <div style="flex:0 0 auto;padding:16px 20px 12px;text-align:right;font-size:48px;color:#fff;font-weight:300;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-height:70px;display:flex;align-items:flex-end;justify-content:flex-end;">
        {{ display }}
      </div>
      <div style="flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:1px;padding:0 1px 1px;">
        <div @click="clear" style="background:#a5a5a5;color:#000;display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer;border-radius:0;">
          {{ currentValue != null || display !== '0' ? 'C' : 'AC' }}
        </div>
        <div @click="toggleSign" style="background:#a5a5a5;color:#000;display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer;">+/-</div>
        <div @click="inputPercent" style="background:#a5a5a5;color:#000;display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer;">%</div>
        <div @click="performOperation('/')" :style="{background: operator==='/' && waitingForOperand ? '#fff' : '#ff9f0a', color: operator==='/' && waitingForOperand ? '#ff9f0a' : '#fff', display:'flex',alignItems:'center',justifyContent:'center',fontSize:'24px',cursor:'pointer'}">÷</div>

        <div @click="inputDigit(7)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">7</div>
        <div @click="inputDigit(8)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">8</div>
        <div @click="inputDigit(9)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">9</div>
        <div @click="performOperation('*')" :style="{background: operator==='*' && waitingForOperand ? '#fff' : '#ff9f0a', color: operator==='*' && waitingForOperand ? '#ff9f0a' : '#fff', display:'flex',alignItems:'center',justifyContent:'center',fontSize:'24px',cursor:'pointer'}">×</div>

        <div @click="inputDigit(4)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">4</div>
        <div @click="inputDigit(5)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">5</div>
        <div @click="inputDigit(6)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">6</div>
        <div @click="performOperation('-')" :style="{background: operator==='-' && waitingForOperand ? '#fff' : '#ff9f0a', color: operator==='-' && waitingForOperand ? '#ff9f0a' : '#fff', display:'flex',alignItems:'center',justifyContent:'center',fontSize:'24px',cursor:'pointer'}">−</div>

        <div @click="inputDigit(1)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">1</div>
        <div @click="inputDigit(2)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">2</div>
        <div @click="inputDigit(3)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">3</div>
        <div @click="performOperation('+')" :style="{background: operator==='+' && waitingForOperand ? '#fff' : '#ff9f0a', color: operator==='+' && waitingForOperand ? '#ff9f0a' : '#fff', display:'flex',alignItems:'center',justifyContent:'center',fontSize:'24px',cursor:'pointer'}">+</div>

        <div @click="inputDigit(0)" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;grid-column:span 2;">0</div>
        <div @click="inputDot" style="background:#333;color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;cursor:pointer;">.</div>
        <div @click="equals" style="background:#ff9f0a;color:#fff;display:flex;align-items:center;justify-content:center;font-size:24px;cursor:pointer;">=</div>
      </div>
    </div>
  `
};
