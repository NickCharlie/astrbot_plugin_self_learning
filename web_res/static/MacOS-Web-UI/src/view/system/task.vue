<template>
  <div class="task">
    <div class="task-list">
      <template v-for="item in $store.state.openAppList"
                :key="item.pid">
        <div class="task-item"
             :class="app && app.pid == item.pid ? 'active' : ''"
             @click="selectApp(item)">
          <i class="iconfont"
             :class="item.icon"
             :style="{
              backgroundColor: item.iconBgColor,
              color: item.iconColor,
            }"></i>
          <span class="task-name">{{ item.title }}</span>
        </div>
      </template>
    </div>
    <div class="task-ctrl">
      <el-button size="mini"
                 type="primary"
                 :disabled="!app.pid"
                 @click="closeApp">强制退出</el-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.task {
  display: flex;
  flex-direction: column;
  height: 350px;
  width: 100%;
  color: #333;
  text-shadow: none;
  font-weight: 300;
  overflow: hidden;
  margin: 10px 20px;
  .task-list {
    display: flex;
    flex: 1;
    flex-direction: column;
    overflow: hidden;
    overflow-y: auto;
    .task-item {
      padding: 8px 16px;
      display: flex;
      margin: 2px 5px;
      flex-direction: row;
      font-size: 14px;
      cursor: pointer;
      border-radius: 5px;
      align-items: center;
      .task-name {
        flex-grow: 1;
        text-overflow: ellipsis;
        word-break: keep-all;
        overflow: hidden;
      }
      .iconfont {
        background: red;
        color: white;
        border-radius: 10px;
        width: 30px;
        height: 30px;
        text-align: center;
        display: flex;
        justify-content: center;
        align-items: center;
        margin-right: 10px;
      }
    }

    .task-item:hover {
      background: rgb(75, 158, 251);
      color: white;
    }
    .active {
      background: rgb(75, 158, 251);
      color: white;
    }
  }
  .task-ctrl {
    justify-content: flex-end;
    align-items: center;
    display: flex;
    padding: 0px 10px;
    margin-top: 10px;
  }
}
</style>
<script setup>
import { reactive, defineEmits } from 'vue'
const emit = defineEmits(['api'])
let app = reactive({})
const selectApp = (item) => {
  Object.assign(app, item);
}
const closeApp = () => {
  if (app.pid) {
    emit("api", {
      event: "closeApp",
      pid: app.pid,
    });
  }
}
</script>