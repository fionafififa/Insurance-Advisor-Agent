import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Form, Input, Modal } from 'antd';
import { useState } from 'react';

import { ApiError, login } from './api';
import type { AuthSession } from './types';

interface AuthModalProps {
  open: boolean;
  onCancel: () => void;
  onSuccess: (session: AuthSession) => void;
}

interface AuthFormValues {
  username: string;
  password: string;
}

export function AuthModal({
  open,
  onCancel,
  onSuccess,
}: AuthModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit({ username, password }: AuthFormValues) {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      onSuccess(await login(username.trim(), password));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : '登录失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  }

  function cancel() {
    if (submitting) return;
    setError(null);
    onCancel();
  }

  return (
    <Modal
      open={open}
      title={null}
      footer={null}
      width={420}
      onCancel={cancel}
      closable={!submitting}
      keyboard={!submitting}
      maskClosable={!submitting}
      destroyOnHidden
      centered
    >
      <div className="auth-modal__header">
        <h2>欢迎来到安心保</h2>
        <p>登录后可使用智能顾问服务</p>
      </div>
      <Form<AuthFormValues>
        layout="vertical"
        onFinish={submit}
        requiredMark={false}
        preserve={false}
        disabled={submitting}
      >
        {error && <Alert showIcon type="error" message={error} />}
        <Form.Item
          label="用户名或邮箱"
          name="username"
          rules={[{ required: true, whitespace: true, message: '请输入用户名或邮箱' }]}
        >
          <Input prefix={<UserOutlined />} size="large" autoComplete="username" />
        </Form.Item>
        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, message: '请输入密码' }]}
        >
          <Input.Password prefix={<LockOutlined />} size="large" autoComplete="current-password" />
        </Form.Item>
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? '登录中…' : '登录'}
        </button>
      </Form>
    </Modal>
  );
}
