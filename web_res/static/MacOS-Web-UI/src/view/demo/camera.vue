<template>
  <div class="demo">
    <div class="preview">
      <video ref="video" :width="width"></video>
      <div class="shooted-preview" v-if="nowPreview">
        <img
          class="shooted-preview-photo"
          :src="'data:image/png;base64,' + nowPreview"
        />
      </div>
      <div
        class="shooted-list"
        :style="nowPreview ? `top: -${height}px` : 'top: -60px'"
        v-if="shootedList.length > 0"
      >
        <div
          style="display: inline-block"
          v-for="(photo, index) in shootedList"
          v-bind:key="photo"
        >
          <div class="shooted-del">
            <i @click="deletePhoto(index)" class="el-icon-error"></i>
          </div>
          <img
            @click="preview(photo)"
            class="photo"
            :src="'data:image/png;base64,' + photo"
          />
        </div>
      </div>
    </div>
    <div class="toolbar" v-if="canUse">
      <el-radio-group
        :style="nowPreview ? 'visibility:hidden;' : ''"
        v-model="mode"
        size="mini"
        text-color="#fff"
        fill="#A0A0A0"
      >
        <el-radio-button label="fourPhoto"
          ><i class="el-icon-menu"></i
        ></el-radio-button>
        <el-radio-button label="portrait"
          ><i class="el-icon-s-custom"></i
        ></el-radio-button>
        <el-radio-button label="video"
          ><i class="el-icon-video-camera"></i
        ></el-radio-button>
      </el-radio-group>
      <div class="tool-action">
        <el-avatar
          :class="nowPreview ? 'back-shoot' : 'shoot-btn'"
          @click="shoot"
        >
          <i class="iconfont icon-camera_fill shoot-icon"></i>
        </el-avatar>
      </div>
      <el-button size="mini" v-if="!nowPreview">效果</el-button>
      <el-button size="mini" @click="download()" v-else>分享</el-button>
      <canvas
        ref="canvas"
        style="display: none"
        :width="width"
        :height="height"
      ></canvas>
    </div>
    <div class="title" v-else>浏览器不支持</div>
  </div>
</template>

<style scoped>
.demo {
  display: flex;
  height: 100%;
  width: 100%;
  margin-top: 0;
  color: #333;
  text-shadow: none;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
}
.preview {
  height: 405px;
  width: 540px;
}
.shooted-preview {
  width: 540px;
  height: 345px;
  position: relative;
  bottom: 405px;
  background-color: #000;
  background-repeat: no-repeat;
  z-index: 1;
}
.shooted-preview-photo {
  width: 540px;
  height: 405px;
}
.shooted-del {
  position: relative;
  top: 0;
  left: 0;
  width: 3px;
  height: 3px;
  z-index: 3;
}
.toolbar {
  display: flex;
  width: 540px;
  height: 50px;
  justify-content: space-between;
  align-items: center;
  margin: 10px;
}
.shooted-list {
  width: 535px;
  height: 60px;
  position: relative;
  bottom: 60px;
  background-color: #f4e5ecf7;
  overflow-x: scroll;
  overflow-y: hidden;
  white-space: nowrap;
  text-align: right;
  z-index: 2;
}
.shoot-btn {
  background-color: red;
}
.back-shoot {
  background-color: gray;
}
.tool-action {
  width: 130px;
}
.shoot-icon {
  color: white;
  font-size: 24px;
}
.photo {
  width: 50px;
  height: 50px;
  background-color: #000;
  background-repeat: no-repeat;
  margin: 5px;
}
.title {
  font-size: 24px;
  text-align: left;
  margin: 10%;
}
</style>
<script>
export default {
  data() {
    return {
      canUse: false,
      width: 540,
      height: 405,
      mode: "portrait",
      nowPreview: "",
      shootedList: [],
    };
  },
  mounted() {
    try {
      this.getCamera();
    } catch (e) {
      console.log(e);
    }
  },
  beforeUnmount() {
    try {
      var videoEl = this.$refs.video;
      var stream = videoEl.srcObject;
      var tracks = stream.getTracks();
      tracks.forEach(function (track) {
        track.stop();
      });
      videoEl.srcObject = null;
    } catch ($e) {
      console.log("关闭摄像头异常", $e);
    }
  },
  methods: {
    getCamera() {
      //这段代 主要是获取摄像头的视频流并显示在Video 签中
      var video = this.$refs.video;
      function successCallback(stream) {
        // Set the source of the video element with the stream from the camera
        if (video.mozSrcObject !== undefined) {
          video.mozSrcObject = stream;
        } else {
          video.srcObject = stream;
        }
        video.play();
      }

      function errorCallback(error) {
        alert("错误代码: [CODE " + error.code + "]");
        // Display a friendly "sorry" message to the user
      }
      navigator.getUserMedia =
        navigator.getUserMedia ||
        navigator.webkitGetUserMedia ||
        navigator.mozGetUserMedia ||
        navigator.msGetUserMedia;
      window.URL =
        window.URL || window.webkitURL || window.mozURL || window.msURL;

      // Call the getUserMedia method with our callback functions
      if (navigator.getUserMedia) {
        this.canUse = true;
        navigator.getUserMedia({ video: true }, successCallback, errorCallback);
      } else {
        alert("浏览器不支持getUserMedia方法调用摄像头", navigator.getUserMedia);
        // Display a friendly "sorry" message to the user
      }
    },
    shoot() {
      if (this.nowPreview) {
        this.nowPreview = "";
        return;
      }
      var content = this.$refs.canvas.getContext("2d");
      var video = this.$refs.video;
      content.drawImage(video, 0, 0, 540, 405);
      //获取浏览器页面的画布对象
      var canvas = this.$refs.canvas;
      //以下开始编码数据
      var imgData = canvas.toDataURL();
      //将图像转换为base64数据
      var base64Data = imgData.substr(22);
      //将获得的base64数据加入shootedList数组
      this.shootedList.push(base64Data);
    },
    preview(photo) {
      this.nowPreview = photo;
    },
    deletePhoto(index) {
      let shootedList = this.shootedList;
      shootedList.splice(index, 1);
      this.shootedList = shootedList;
      if (this.nowPreview && shootedList.length == 0) {
        this.shoot();
      }
    },
    base64Img2Blob(code) {
      var parts = code.split(";base64,");
      var contentType = parts[0].split(":")[1];
      var raw = window.atob(parts[1]);
      var rawLength = raw.length;

      var uInt8Array = new Uint8Array(rawLength);

      for (var i = 0; i < rawLength; ++i) {
        uInt8Array[i] = raw.charCodeAt(i);
      }

      return new Blob([uInt8Array], { type: contentType });
    },
    download() {
      let canvasID = this.$refs.canvas;
      let download = document.createElement("a");
      let blob = this.base64Img2Blob(canvasID.toDataURL("image/png"));
      download.setAttribute("href", URL.createObjectURL(blob));
      download.setAttribute("download", new Date().getTime() + ".png");
      document.body.appendChild(download);
      download.click();
      URL.revokeObjectURL(blob);
      document.body.removeChild(download);
    },
  },
};
</script>