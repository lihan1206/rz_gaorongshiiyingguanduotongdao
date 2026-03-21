import { Button, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd';
import dayjs from 'dayjs';

import { api } from '../api/client';
import PageShell from '../components/PageShell';

const AlarmsPage = ({ alarms, loading, onRefresh }) => {
  const handleResolve = async (id) => {
    try {
      await api.resolveAlarm(id, true);
      message.success('报警已确认处理');
      onRefresh();
    } catch (error) {
      message.error(error.message || '处理失败');
    }
  };

  const levelTag = (value) => {
    const map = {
      high: <Tag color="red">高液位</Tag>,
      low: <Tag color="orange">低液位</Tag>,
      drift: <Tag color="purple">漂移</Tag>,
    };
    return map[value] || <Tag>{value}</Tag>;
  };

  const columns = [
    { title: '报警ID', dataIndex: 'id', key: 'id', width: 80 },
    { title: '通道', dataIndex: 'channel_name', key: 'channel_name', width: 100 },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 90,
      render: (value) => levelTag(value),
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
    {
      title: '传感器A',
      dataIndex: 'value_a',
      key: 'value_a',
      render: (value) => (value !== null ? Number(value).toFixed(2) : '-'),
    },
    {
      title: '传感器B',
      dataIndex: 'value_b',
      key: 'value_b',
      render: (value) => (value !== null ? Number(value).toFixed(2) : '-'),
    },
    {
      title: '数据源',
      dataIndex: 'sensor_source',
      key: 'sensor_source',
      width: 180,
      render: (value) => (
        <Tooltip title={value}>
          <Tag color="blue" style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {value}
          </Tag>
        </Tooltip>
      ),
    },
    { 
      title: '描述', 
      dataIndex: 'description', 
      key: 'description',
      ellipsis: true,
    },
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      key: 'occurred_at',
      width: 160,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '处理状态',
      dataIndex: 'resolved',
      key: 'resolved',
      width: 100,
      render: (resolved) => (resolved ? <Tag color="green">已处理</Tag> : <Tag color="red">待处理</Tag>),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) =>
        record.resolved ? (
          <Tag color="default">已完成</Tag>
        ) : (
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
      <Table rowKey="id" dataSource={alarms} columns={columns} scroll={{ x: 1500 }} />
    </PageShell>
  );
};

export default AlarmsPage;
