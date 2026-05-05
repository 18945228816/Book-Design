<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { userApi } from '../api'

const router = useRouter()
const isLogin = ref(true)
const loading = ref(false)

const form = ref({
  email: '',
  password: '',
  username: ''
})

const handleSubmit = async () => {
  if (!form.value.email || !form.value.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }

  if (!isLogin.value && !form.value.username) {
    ElMessage.warning('请填写用户名')
    return
  }

  loading.value = true
  try {
    let res
    if (isLogin.value) {
      res = await userApi.login({
        email: form.value.email,
        password: form.value.password
      })
    } else {
      res = await userApi.register({
        email: form.value.email,
        password: form.value.password,
        username: form.value.username
      })
    }

    localStorage.setItem('token', res.token)
    localStorage.setItem('user', JSON.stringify(res))
    ElMessage.success(isLogin.value ? '登录成功' : '注册成功')
    router.push('/')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header>
        <h2>{{ isLogin ? '登录' : '注册' }}</h2>
      </template>

      <el-form label-width="80px">
        <el-form-item v-if="!isLogin" label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit" style="width: 100%">
            {{ isLogin ? '登录' : '注册' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="switch-mode">
        <span>{{ isLogin ? '没有账号？' : '已有账号？' }}</span>
        <el-button type="primary" link @click="isLogin = !isLogin">
          {{ isLogin ? '立即注册' : '立即登录' }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
}

h2 {
  text-align: center;
  margin: 0;
}

.switch-mode {
  text-align: center;
  margin-top: 10px;
}
</style>
