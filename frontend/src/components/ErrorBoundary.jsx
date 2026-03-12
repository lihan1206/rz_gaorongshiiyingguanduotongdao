import React from 'react';
import { Alert, Button } from 'antd';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <Alert
            type="error"
            showIcon
            message="页面加载异常"
            description="系统捕获到一个运行错误，请刷新页面重试。"
            action={
              <Button size="small" danger onClick={this.handleReload}>
                立即刷新
              </Button>
            }
          />
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
