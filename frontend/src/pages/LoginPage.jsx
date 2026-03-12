import { Button, Card, Form, Input, Typography } from 'antd';

const { Title, Text } = Typography;

const LoginPage = ({ onLogin, loading }) => {
  return (
    <div className="login-wrapper">
      <Card className="login-card">
        <Title level={3} className="login-title">
          系统登录
        </Title>
        <Text className="login-subtitle">高融石英管多通道液位同步检测系统</Text>

        <Form layout="vertical" onFinish={onLogin} className="login-form">
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="请输入用户名" size="large" />
          </Form.Item>

          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="请输入密码" size="large" />
          </Form.Item>

          <Button type="primary" htmlType="submit" block size="large" loading={loading}>
            登录
          </Button>
        </Form>

        <Text className="login-tip">测试账号：admin / 123456</Text>
      </Card>
    </div>
  );
};

export default LoginPage;
