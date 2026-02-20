<template>
  <div class="demo">
    <div class="title">
      我允许被多次打开，但我无法被固定在Dock上，<br />因为我的 keepInDock 在
      <br />multiTask = true 时将自动失效
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