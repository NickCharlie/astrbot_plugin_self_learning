<template>
  <div class="finder">
    <div class="list-left"></div>
  </div>
</template>

<script>
export default {
  data() {
    return {};
  },
  created() {},
};
</script>

<style scoped lang="scss">
.finder {
  --resize: 5px;
  --resize-bg: transparent;
  --resize-main: transparent;
  --resize-bg-main: transparent;
}
.finder {
  display: flex;
  flex-direction: column;
  height: 350px;
  width: 100%;
  color: #333;
  text-shadow: none;
  font-weight: 300;
  overflow: hidden;
  .list-left {
    position: absolute;
    top: 40px;
    bottom: 0px;
    width: 200px;
    height: 100%;
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(20px);
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
  }
}
</style>
