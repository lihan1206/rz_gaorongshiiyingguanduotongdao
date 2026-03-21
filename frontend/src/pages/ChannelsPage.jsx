import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { api } from '../api/client';
import PageShell from '../components/PageShell';

const sensorOptions = [
  { label: '电容式', value: 'capacitive' },
  { label: '超声波', value: 'ultrasonic' },
  { label: '激光位移', value: 'laser' },
];

const alarmTypeOptions = [
  { label: '高液位报警', value: 'high' },
  { label: '低液位报警', value: 'low' },
  { label: '漂移报警', value: 'drift' },
];

const ChannelsPage = ({ channels, loading, onRefresh }) => {
  const [open, setOpen] = useState(false);
  const [thresholdOpen, setThresholdOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [thresholdChannel, setThresholdChannel] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [thresholdForm] = Form.useForm();

  const statusTag = (status) =>
    status === 'active' ? <Tag color="green">运行中</Tag> : <Tag color="default">已停用</Tag>;

  const alarmTypeTag = (type) => {
    const map = {
      high: <Tag color="red">高液位</Tag>,
      low: <Tag color="orange">低液位</Tag>,
      drift: <Tag color="purple">漂移</Tag>,
    };
    return map[type] || <Tag>{type}</Tag>;
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      sensor_type_a: 'capacitive',
      sensor_type_b: 'ultrasonic',
      range_min: 0,
      range_max: 200,
      warning_low: 25,
      warning_high: 175,
      alarm_type: 'high',
      alarm_enabled: true,
      unit: 'mm',
      status: 'active',
      calibration_offset_a: 0,
      calibration_offset_b: 0,
      fusion_weight_a: 0.6,
      fusion_weight_b: 0.4,
    });
    setOpen(true);
  };

  const openEdit = (record) => {
    setEditing(record);
    form.setFieldsValue(record);
    setOpen(true);
  };

  const openThreshold = (record) => {
    setThresholdChannel(record);
    thresholdForm.setFieldsValue({
      warning_low: record.warning_low,
      warning_high: record.warning_high,
      alarm_type: record.alarm_type,
      alarm_enabled: record.alarm_enabled,
    });
    setThresholdOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editing) {
        await api.updateChannel(editing.id, values);
        message.success('通道更新成功');
      } else {
        await api.createChannel(values);
        message.success('通道创建成功');
      }
      setOpen(false);
      onRefresh();
    } catch (error) {
      if (error?.errorFields) {
        return;
      }
      message.error(error.message || '提交失败');
    } finally {
      setSaving(false);
    }
  };

  const handleThresholdSubmit = async () => {
    try {
      const values = await thresholdForm.validateFields();
      setSaving(true);
      await api.updateThreshold(thresholdChannel.id, values);
      message.success('阈值更新成功（热更新，无需重启）');
      setThresholdOpen(false);
      onRefresh();
    } catch (error) {
      if (error?.errorFields) {
        return;
      }
      message.error(error.message || '更新失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.deleteChannel(id);
      message.success('通道删除成功');
      onRefresh();
    } catch (error) {
      message.error(error.message || '删除失败');
    }
  };

  const columns = useMemo(
    () => [
      { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
      { title: '通道名称', dataIndex: 'name', key: 'name', width: 120 },
      {
        title: '传感器A',
        dataIndex: 'sensor_type_a',
        key: 'sensor_type_a',
        render: (value) => sensorOptions.find((item) => item.value === value)?.label || value,
      },
      {
        title: '传感器B',
        dataIndex: 'sensor_type_b',
        key: 'sensor_type_b',
        render: (value) => (value ? sensorOptions.find((item) => item.value === value)?.label || value : '-'),
      },
      {
        title: '融合权重',
        key: 'fusion',
        render: (_, record) => `${record.fusion_weight_a}:${record.fusion_weight_b}`,
      },
      {
        title: '量程',
        key: 'range',
        render: (_, record) => `${record.range_min} ~ ${record.range_max} ${record.unit}`,
      },
      {
        title: '报警阈值',
        key: 'warn',
        render: (_, record) => `${record.warning_low} ~ ${record.warning_high}`,
      },
      {
        title: '报警类型',
        dataIndex: 'alarm_type',
        key: 'alarm_type',
        render: (value) => alarmTypeTag(value),
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        render: (value) => statusTag(value),
      },
      {
        title: '操作',
        key: 'action',
        width: 220,
        render: (_, record) => (
          <Space>
            <Button size="small" onClick={() => openThreshold(record)}>
              阈值
            </Button>
            <Button size="small" onClick={() => openEdit(record)}>
              编辑
            </Button>
            <Popconfirm
              title="确认删除该通道？"
              description="删除后会同时清空该通道的采样数据与报警记录。"
              okText="确认删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => handleDelete(record.id)}
            >
              <Button size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    []
  );

  return (
    <PageShell
      title="通道配置管理"
      loading={loading}
      extra={
        <Button type="primary" onClick={openCreate}>
          新建通道
        </Button>
      }
    >
      <Table rowKey="id" dataSource={channels} columns={columns} scroll={{ x: 1400 }} />

      <Modal
        title={editing ? '编辑通道' : '新建通道'}
        open={open}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        destroyOnClose
        width={720}
      >
        <Form layout="vertical" form={form}>
          <Form.Item label="通道名称" name="name" rules={[{ required: true, message: '请输入通道名称' }]}>
            <Input placeholder="例如：石英管-09" maxLength={50} />
          </Form.Item>

          <Card size="small" title="传感器配置" className="section-gap">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="传感器A类型" name="sensor_type_a" rules={[{ required: true }]}>
                  <Select options={sensorOptions} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="传感器B类型" name="sensor_type_b">
                  <Select options={sensorOptions} allowClear placeholder="可选" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="传感器A校准偏移" name="calibration_offset_a">
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="传感器B校准偏移" name="calibration_offset_b">
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item 
                  label="融合权重A" 
                  name="fusion_weight_a"
                  rules={[{ required: true }]}
                  extra="权重A + 权重B = 1"
                >
                  <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item 
                  label="融合权重B" 
                  name="fusion_weight_b"
                  rules={[{ required: true }]}
                >
                  <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.1} />
                </Form.Item>
              </Col>
            </Row>
          </Card>

          <Card size="small" title="量程与报警" className="section-gap">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label="量程下限" name="range_min" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="量程上限" name="range_max" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="单位" name="unit" rules={[{ required: true }]}>
                  <Input maxLength={10} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item label="报警下限" name="warning_low" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="报警上限" name="warning_high" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item label="报警类型" name="alarm_type" rules={[{ required: true }]}>
                  <Select options={alarmTypeOptions} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="启用报警" name="alarm_enabled" valuePropName="checked">
                  <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="通道状态" name="status" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { label: '运行中', value: 'active' },
                      { label: '已停用', value: 'inactive' },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        </Form>
      </Modal>

      <Modal
        title={`动态阈值调节 - ${thresholdChannel?.name || ''}`}
        open={thresholdOpen}
        confirmLoading={saving}
        okText="热更新"
        cancelText="取消"
        onCancel={() => setThresholdOpen(false)}
        onOk={handleThresholdSubmit}
        destroyOnClose
      >
        <Form layout="vertical" form={thresholdForm}>
          <Alert
            type="info"
            showIcon
            message="热更新说明"
            description="修改阈值后立即生效，无需重启系统。"
            style={{ marginBottom: 16 }}
          />
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="报警下限" name="warning_low">
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="报警上限" name="warning_high">
                <InputNumber style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="报警类型" name="alarm_type">
                <Select options={alarmTypeOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="启用报警" name="alarm_enabled" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </PageShell>
  );
};

export default ChannelsPage;
