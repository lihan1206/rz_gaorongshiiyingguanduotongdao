import { Alert, Button, Card, Col, Form, InputNumber, Row, Space, Table, Tag, message } from 'antd';
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
        value_a: values[`channel_${channel.id}_a`] !== undefined ? Number(values[`channel_${channel.id}_a`]) : null,
        value_b: values[`channel_${channel.id}_b`] !== undefined ? Number(values[`channel_${channel.id}_b`]) : null,
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
      title: '传感器A值(mm)',
      dataIndex: 'value_a',
      key: 'value_a',
      render: (value) => (value !== null ? Number(value).toFixed(2) : '-'),
    },
    {
      title: '传感器B值(mm)',
      dataIndex: 'value_b',
      key: 'value_b',
      render: (value) => (value !== null ? Number(value).toFixed(2) : '-'),
    },
    {
      title: '融合值(mm)',
      dataIndex: 'fused_value',
      key: 'fused_value',
      render: (value) => <strong>{Number(value).toFixed(2)}</strong>,
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
        message="多源传感器融合采样"
        description="每个通道支持双传感器采集（A: 电容式, B: 超声波），系统使用加权平均法融合数据。采集频率建议：100ms。"
      />

      <Form form={form} layout="vertical" className="section-gap">
        <Form.Item label="环境温度(℃)" name="temperature">
          <InputNumber style={{ width: 240 }} placeholder="可选" />
        </Form.Item>

        <div className="sampling-grid-dual">
          {activeChannels.map((channel) => (
            <Card 
              key={channel.id} 
              size="small" 
              title={channel.name}
              extra={<Tag color="blue">权重 {channel.fusion_weight_a}:{channel.fusion_weight_b}</Tag>}
            >
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    label={`传感器A (${channel.sensor_type_a})`}
                    name={`channel_${channel.id}_a`}
                    tooltip={`校准偏移: ${channel.calibration_offset_a}`}
                  >
                    <InputNumber 
                      style={{ width: '100%' }} 
                      min={channel.range_min} 
                      max={channel.range_max} 
                      placeholder="电容值"
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    label={`传感器B (${channel.sensor_type_b || '未配置'})`}
                    name={`channel_${channel.id}_b`}
                    tooltip={`校准偏移: ${channel.calibration_offset_b}`}
                  >
                    <InputNumber 
                      style={{ width: '100%' }} 
                      min={channel.range_min} 
                      max={channel.range_max} 
                      placeholder="超声波值"
                    />
                  </Form.Item>
                </Col>
              </Row>
              <div style={{ fontSize: 12, color: '#888' }}>
                报警阈值: {channel.warning_low} ~ {channel.warning_high} {channel.unit}
              </div>
            </Card>
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
