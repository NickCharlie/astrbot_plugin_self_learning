<template>
  <div class="demo">
    <iframe :src="app.url"></iframe>
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

  iframe {
    width: 100%;
    height: 100%;
    border: none;
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