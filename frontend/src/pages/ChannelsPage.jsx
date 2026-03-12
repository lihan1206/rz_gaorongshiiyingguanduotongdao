import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
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

const ChannelsPage = ({ channels, loading, onRefresh }) => {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const statusTag = (status) =>
    status === 'active' ? <Tag color="green">运行中</Tag> : <Tag color="default">已停用</Tag>;

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      sensor_type: 'capacitive',
      range_min: 0,
      range_max: 200,
      warning_low: 25,
      warning_high: 175,
      alarm_enabled: true,
      unit: 'mm',
      status: 'active',
      calibration_offset: 0,
    });
    setOpen(true);
  };

  const openEdit = (record) => {
    setEditing(record);
    form.setFieldsValue(record);
    setOpen(true);
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
      { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
      { title: '通道名称', dataIndex: 'name', key: 'name', width: 140 },
      {
        title: '传感器类型',
        dataIndex: 'sensor_type',
        key: 'sensor_type',
        render: (value) => sensorOptions.find((item) => item.value === value)?.label || value,
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
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        render: (value) => statusTag(value),
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
      },
      {
        title: '操作',
        key: 'action',
        width: 180,
        render: (_, record) => (
          <Space>
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
      <Table rowKey="id" dataSource={channels} columns={columns} scroll={{ x: 1200 }} />

      <Modal
        title={editing ? '编辑通道' : '新建通道'}
        open={open}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        destroyOnClose
      >
        <Form layout="vertical" form={form}>
          <Form.Item label="通道名称" name="name" rules={[{ required: true, message: '请输入通道名称' }]}>
            <Input placeholder="例如：石英管-09" maxLength={50} />
          </Form.Item>

          <Form.Item label="传感器类型" name="sensor_type" rules={[{ required: true }]}> 
            <Select options={sensorOptions} />
          </Form.Item>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item
              style={{ flex: 1 }}
              label="量程下限"
              name="range_min"
              rules={[{ required: true, message: '请输入量程下限' }]}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              style={{ flex: 1 }}
              label="量程上限"
              name="range_max"
              rules={[{ required: true, message: '请输入量程上限' }]}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item
              style={{ flex: 1 }}
              label="报警下限"
              name="warning_low"
              rules={[{ required: true, message: '请输入报警下限' }]}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              style={{ flex: 1 }}
              label="报警上限"
              name="warning_high"
              rules={[{ required: true, message: '请输入报警上限' }]}
            >
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item style={{ flex: 1 }} label="单位" name="unit" rules={[{ required: true }]}>
              <Input maxLength={10} />
            </Form.Item>
            <Form.Item style={{ flex: 1 }} label="校准偏移" name="calibration_offset" rules={[{ required: true }]}>
              <InputNumber style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item style={{ flex: 1 }} label="启用报警" name="alarm_enabled" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
            <Form.Item style={{ flex: 1 }} label="通道状态" name="status" rules={[{ required: true }]}> 
              <Select
                options={[
                  { label: '运行中', value: 'active' },
                  { label: '已停用', value: 'inactive' },
                ]}
              />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </PageShell>
  );
};

export default ChannelsPage;
