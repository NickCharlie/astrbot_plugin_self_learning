<template>
  <div class="demo">
    <div class="title">
      我被设置了 hideInDesktop ，
      <br />不会出现在桌面上，如果把keepInDock设置false，<br />我就跟关于那个一样，也不出现在Dock上
    </div>
    <el-button size="small" type="primary" @click="openAbout"
      >看看关于长什么样</el-button
    >
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
  flex-direction: column;

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
  methods: {
    openAbout() {
      this.$emit("api", {
        event: "openApp",
        app: "system_about",
      });
    },
  },
};
</script>