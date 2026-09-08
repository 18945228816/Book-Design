<script setup>
import { ref, computed, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { userApi } from '../api'

const router = useRouter()
const isLogin = ref(true)
const loading = ref(false)
const formRef = ref(null)

const form = ref({
  email: '',
  password: '',
  username: '',
  code: ''
})

// 验证码发送状态
const sending = ref(false)
const countdown = ref(0)
let timer = null

const codeButtonText = computed(() =>
  countdown.value > 0 ? `${countdown.value}秒后重发` : '发送验证码'
)

const startCountdown = (seconds = 60) => {
  countdown.value = seconds
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}

// 组件卸载时清掉定时器，避免离开页面后仍在跑
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const handleSendCode = async () => {
  // 只校验邮箱一项，避免用户名/密码为空时挡住发码
  const emailOk = await formRef.value
    .validateField('email')
    .then(() => true)
    .catch(() => false)
  if (!emailOk) return

  sending.value = true
  try {
    const res = await userApi.sendCode({ email: form.value.email })
    ElMessage.success(res.message || '验证码已发送，请查收邮件')
    startCountdown()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    sending.value = false
  }
}

const rules = computed(() => {
  const base = {
    email: [
      { required: true, type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
    ],
    password: [
      { required: true, min: 6, message: '密码至少6位', trigger: 'blur' }
    ]
  }
  if (!isLogin.value) {
    base.username = [
      { required: true, message: '请输入用户名', trigger: 'blur' }
    ]
    base.code = [
      { required: true, message: '请输入验证码', trigger: 'blur' },
      { pattern: /^\d{6}$/, message: '验证码为6位数字', trigger: 'blur' }
    ]
  }
  return base
})

const switchMode = async () => {
  isLogin.value = !isLogin.value
  form.value.code = ''
  // 等 rules/字段随模式切换渲染完，再清校验状态，否则清的是旧字段
  await nextTick()
  formRef.value?.clearValidate()
}

const handleSubmit = async () => {
  // 校验不通过时 validate() 会 reject，此处吞掉异常并中止提交
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

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
        username: form.value.username,
        code: form.value.code
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

      <!-- validate-on-rule-change=false: rules 是 computed，切换登录/注册时会重建，
           默认行为会立刻全表单校验并弹出一片红字，这里关掉 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        :validate-on-rule-change="false"
        label-width="80px"
        @submit.prevent
      >
        <el-form-item v-if="!isLogin" label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item v-if="!isLogin" label="验证码" prop="code">
          <div class="code-row">
            <el-input v-model="form.code" placeholder="6位验证码" maxlength="6" />
            <el-button
              :loading="sending"
              :disabled="countdown > 0"
              @mousedown.prevent
              @click.stop="handleSendCode"
            >
              {{ codeButtonText }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password
            @keyup.enter="handleSubmit" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit" style="width: 100%">
            {{ isLogin ? '登录' : '注册' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="switch-mode">
        <span>{{ isLogin ? '没有账号？' : '已有账号？' }}</span>
        <el-button type="primary" link @click="switchMode">
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

.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-row .el-input {
  flex: 1;
}

.code-row .el-button {
  flex-shrink: 0;
  min-width: 104px;
}
</style>
