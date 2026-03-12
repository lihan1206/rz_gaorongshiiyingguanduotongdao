import { Button, Popconfirm, Space, Table, Tag, message } from 'antd';
import dayjs from 'dayjs';

import { api } from '../api/client';
import PageShell from '../components/PageShell';

const AlarmsPage = ({ alarms, loading, onRefresh }) => {
  const handleResolve = async (id) => {
    try {
      await api.resolveAlarm(id);
      message.success('报警已确认处理');
      onRefresh();
    } catch (error) {
      message.error(error.message || '处理失败');
    }
  };

  const columns = [
    { title: '报警ID', dataIndex: 'id', key: 'id', width: 90 },
    { title: '通道', dataIndex: 'channel_name', key: 'channel_name', width: 120 },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      render: (value) => (value === 'high' ? <Tag color="red">高液位</Tag> : <Tag color="orange">低液位</Tag>),
    },
    {
      title: '阈值',
      dataIndex: 'threshold',
      key: 'threshold',
      render: (value) => Number(value).toFixed(2),
    },
    {
      title: '实际值',
      dataIndex: 'actual_value',
      key: 'actual_value',
      render: (value) => Number(value).toFixed(2),
    },
    { title: '描述', dataIndex: 'description', key: 'description' },
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      key: 'occurred_at',
      width: 170,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '处理状态',
      dataIndex: 'resolved',
      key: 'resolved',
      width: 120,
      render: (resolved) => (resolved ? <Tag color="green">已处理</Tag> : <Tag color="red">待处理</Tag>),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) =>
        record.resolved ? (
          <Tag color="default">已完成</Tag>
        ) : (
          <Space>
            <Popconfirm
              title="确认标记为已处理？"
              description="该操作将记录处理时间。"
              okText="确认"
              cancelText="取消"
              onConfirm={() => handleResolve(record.id)}
            >
              <Button size="small" type="primary">
                确认处理
              </Button>
            </Popconfirm>
          </Space>
        ),
    },
  ];

  return (
    <PageShell
      title="报警中心"
      loading={loading}
      extra={
        <Button onClick={onRefresh}>
          刷新列表
        </Button>
      }
    >
      <Table rowKey="id" dataSource={alarms} columns={columns} scroll={{ x: 1200 }} />
    </PageShell>
  );
};

export default AlarmsPage;
