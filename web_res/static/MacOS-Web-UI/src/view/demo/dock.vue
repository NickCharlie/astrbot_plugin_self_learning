<template>
  <div class="demo">
    <div class="title">
      我是一个常驻Dock上的App，<br />关闭后也一直在Dock上，<br />你可以通过配置
      keepInDock 来修饰我
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
  created() {},
};
</script>