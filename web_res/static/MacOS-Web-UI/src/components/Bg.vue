<template>
  <div class="bg" :style="{ filter:'blur('+blur+')', backgroundImage: 'url(' + bgImage + ')' }"></div>
</template>

<style scoped lang="scss">
.bg {
  background-color: #000;
  position: fixed;
  object-fit: cover;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  z-index: 0;
  background-size: cover;
  background-repeat: no-repeat;
}

</style>
<script>
export default {
  props:['blur'],
  data() {
    return {
      bgImage: require("@/asset/img/bg.jpg"),
    };
  },
};
</script>