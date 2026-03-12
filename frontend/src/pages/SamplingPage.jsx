import { Alert, Button, Form, InputNumber, Space, Table, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { api } from '../api/client';
import PageShell from '../components/PageShell';

const SamplingPage = ({ channels, loading, onAfterSync }) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState([]);

  const activeChannels = useMemo(() => channels.filter((item) => item.status === 'active'), [channels]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const points = activeChannels.map((channel) => ({
        channel_id: channel.id,
        value: Number(values[`channel_${channel.id}`]),
      }));

      setSubmitting(true);
      const result = await api.syncSamples({
        temperature: values.temperature,
        values: points,
      });
      setLastResult(result);
      message.success('同步采样已写入数据库');
      onAfterSync();
    } catch (error) {
      if (error?.errorFields) {
        return;
      }
      message.error(error.message || '同步采样失败');
    } finally {
      setSubmitting(false);
    }
  };

  const resultColumns = [
    { title: '记录ID', dataIndex: 'id', key: 'id' },
    { title: '通道ID', dataIndex: 'channel_id', key: 'channel_id' },
    {
      title: '液位值(mm)',
      dataIndex: 'value',
      key: 'value',
      render: (value) => Number(value).toFixed(2),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const color = status === 'normal' ? 'green' : status === 'warning' ? 'gold' : 'red';
        return <Tag color={color}>{status.toUpperCase()}</Tag>;
      },
    },
    {
      title: '采样时间',
      dataIndex: 'sample_time',
      key: 'sample_time',
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
  ];

  return (
    <PageShell title="同步采样录入" loading={loading}>
      <Alert
        type="info"
        showIcon
        message="说明"
        description="该模块用于将每个在线通道的实时采样值一次性同步写入数据库，并触发阈值报警判定。"
      />

      <Form form={form} layout="vertical" className="section-gap">
        <Form.Item label="环境温度(℃)" name="temperature">
          <InputNumber style={{ width: 240 }} placeholder="可选" />
        </Form.Item>

        <div className="sampling-grid">
          {activeChannels.map((channel) => (
            <Form.Item
              key={channel.id}
              label={`${channel.name} (${channel.warning_low}-${channel.warning_high}${channel.unit})`}
              name={`channel_${channel.id}`}
              rules={[{ required: true, message: '请输入液位值' }]}
            >
              <InputNumber style={{ width: '100%' }} min={channel.range_min} max={channel.range_max} />
            </Form.Item>
          ))}
        </div>

        <Space>
          <Button type="primary" loading={submitting} onClick={handleSubmit}>
            执行同步采样
          </Button>
          <Button onClick={() => form.resetFields()}>重置</Button>
        </Space>
      </Form>

      <div className="section-gap">
        <h3 className="section-title">最近一次同步结果</h3>
        <Table rowKey="id" dataSource={lastResult} columns={resultColumns} pagination={false} locale={{ emptyText: '暂无记录' }} />
      </div>
    </PageShell>
  );
};

export default SamplingPage;
