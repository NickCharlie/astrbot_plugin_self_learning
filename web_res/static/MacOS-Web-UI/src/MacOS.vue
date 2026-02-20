<template>
  <div class="mac-os"
       @mousedown.self="boot"
       @contextmenu.prevent="onContextShow()">
    <transition name="fade">
      <Bg v-if="isBg"></Bg>
    </transition>
    <transition name="fade">
      <Loading v-if="isLoading"
               @loaded="loaded"></Loading>
    </transition>
    <transition name="fade">
      <Login v-if="isLogin"
             @logined="logined"></Login>
    </transition>
    <transition name="fade">
      <DeskTop
        v-if="isDeskTop"
        @lockScreen="lockScreen"
        @shutdown="shutdown"
        @logout="logout"
        @launchpad="launchpad"
      ></DeskTop>
    </transition>
    <transition name="fade">
      <LaunchPad v-if="isLaunchPad"></LaunchPad>
    </transition>
  </div>
</template>

<style scoped lang="scss">
.mac-os {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
}
</style>
<script setup>
import Bg from "@/components/Bg";
import LaunchPad from "@/components/LaunchPad";
import Loading from "@/components/Loading";
import Login from "@/components/Login";
import DeskTop from "@/components/DeskTop";

import { ref, onMounted } from 'vue'
let isBg = ref(true)
let isLoading = ref(false)
let isLogin = ref(false)
let isDeskTop = ref(false)
let isLaunchPad = ref(false)

onMounted(() => {
  boot();
})
const onContextShow = () => {
  console.log("onContextShow");
}
const boot = () => {
  isLoading.value = true;
}
const loaded = () => {
  isLoading.value = false;
  isBg.value = true;
  isLogin.value = true;
}
const logined = () => {
  isLogin.value = false;
  isDeskTop.value = true;
}
const lockScreen = () => {
  isLogin.value = true;
}
const launchpad = (show) => {
  isLaunchPad.value = show;
}
const logout = () => {
  localStorage.removeItem("user_name");
  isDeskTop.value = false;
  isLogin.value = true;
}
const shutdown = () => {
  localStorage.removeItem("user_name");
  isDeskTop.value = false;
  isLogin.value = false;
  isLoading.value = false;
  isBg.value = false;
}
</script>
