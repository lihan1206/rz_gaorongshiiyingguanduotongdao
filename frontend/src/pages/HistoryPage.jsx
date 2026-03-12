import { Button, DatePicker, Empty, Form, Select, Space, Table, Tag, message } from 'antd';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';

import { api } from '../api/client';
import PageShell from '../components/PageShell';

const { RangePicker } = DatePicker;

const HistoryPage = ({ channels, loading }) => {
  const [form] = Form.useForm();
  const [records, setRecords] = useState([]);
  const [querying, setQuerying] = useState(false);

  const handleQuery = async () => {
    try {
      const values = await form.validateFields();
      const params = {
        channel_id: values.channel_id,
      };

      if (values.range && values.range.length === 2) {
        params.start = values.range[0].toISOString();
        params.end = values.range[1].toISOString();
      }

      setQuerying(true);
      const data = await api.listSamples(params);
      setRecords(data);
      message.success(`查询到 ${data.length} 条记录`);
    } catch (error) {
      if (error?.errorFields) {
        return;
      }
      message.error(error.message || '查询失败');
    } finally {
      setQuerying(false);
    }
  };

  const handleExport = async () => {
    try {
      const values = form.getFieldsValue();
      const params = {};
      if (values.range && values.range.length === 2) {
        params.start = values.range[0].toISOString();
        params.end = values.range[1].toISOString();
      }
      const response = await api.exportSamples(params);
      const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `液位历史报表_${dayjs().format('YYYYMMDD_HHmmss')}.csv`;
      link.click();
      window.URL.revokeObjectURL(url);
      message.success('报表导出成功');
    } catch (error) {
      message.error(error.message || '报表导出失败');
    }
  };

  const chartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: records.map((item) => dayjs(item.sample_time).format('MM-DD HH:mm')),
      },
      yAxis: {
        type: 'value',
        name: '液位(mm)',
      },
      series: [
        {
          type: 'line',
          smooth: true,
          data: records.map((item) => item.value),
          symbol: 'none',
          lineStyle: { width: 2, color: '#13c2c2' },
          areaStyle: { color: 'rgba(19, 194, 194, 0.18)' },
        },
      ],
    }),
    [records]
  );

  const columns = [
    { title: '记录ID', dataIndex: 'id', key: 'id', width: 100 },
    { title: '通道ID', dataIndex: 'channel_id', key: 'channel_id', width: 100 },
    {
      title: '液位值(mm)',
      dataIndex: 'value',
      key: 'value',
      render: (value) => Number(value).toFixed(2),
    },
    {
      title: '温度(℃)',
      dataIndex: 'temperature',
      key: 'temperature',
      render: (value) => (value === null ? '--' : Number(value).toFixed(2)),
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
    <PageShell title="历史数据查询与报表" loading={loading}>
      <Form form={form} layout="inline" className="history-form">
        <Form.Item label="通道" name="channel_id" rules={[{ required: true, message: '请选择通道' }]}>
          <Select
            style={{ width: 180 }}
            placeholder="请选择通道"
            options={channels.map((item) => ({ label: item.name, value: item.id }))}
          />
        </Form.Item>

        <Form.Item label="时间范围" name="range">
          <RangePicker showTime />
        </Form.Item>

        <Space>
          <Button type="primary" loading={querying} onClick={handleQuery}>
            查询
          </Button>
          <Button onClick={handleExport}>导出 CSV</Button>
        </Space>
      </Form>

      <div className="section-gap">
        <h3 className="section-title">趋势分析</h3>
        {records.length > 0 ? <ReactECharts option={chartOption} style={{ height: 280 }} /> : <Empty description="请先执行查询" />}
      </div>

      <div className="section-gap">
        <h3 className="section-title">明细记录</h3>
        <Table rowKey="id" dataSource={records} columns={columns} scroll={{ x: 1000 }} />
      </div>
    </PageShell>
  );
};

export default HistoryPage;
