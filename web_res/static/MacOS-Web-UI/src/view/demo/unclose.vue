<template>
  <div class="demo">
    <div class="title">
      我无法被彻底关闭，只会被隐藏，<br />因为我 hideWhenClose = true ,
      <br />你猜我适合做什么应用？
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