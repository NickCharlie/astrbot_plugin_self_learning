
<template>
  <div class="demo">
    <div class="title">
      我的标题栏花里胡哨 <br />你可以通过设置 <br />titleBgColor/titleColor
      来修饰我

      <div style="color: red">{{ app && app.data }}</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.demo {
  display: flex;
  height: 100%;
  width: 100%;
  color: #333;
  text-shadow: none;
  justify-content: center;
  align-items: center;
  .title {
    font-size: 16px;
    text-align: left;
    margin: 10%;
  }
}
</style>
<script>
export default {
  data() {
    return {};
  },
  props: {
    app: Object,
  },
  created() {},
};
</script>