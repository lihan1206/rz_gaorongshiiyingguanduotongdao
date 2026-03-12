import { Card, Skeleton } from 'antd';

const PageShell = ({ title, loading, extra, children }) => (
  <Card title={title} extra={extra} className="glass-card">
    {loading ? <Skeleton active paragraph={{ rows: 8 }} /> : children}
  </Card>
);

export default PageShell;
