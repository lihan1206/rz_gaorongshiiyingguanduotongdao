import { Col, Empty, Row, Statistic, Table, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';

import PageShell from '../components/PageShell';

const statusColorMap = {
  normal: 'green',
  warning: 'gold',
  error: 'red',
};

const DashboardPage = ({ summary, trendData, selectedChannelId, onSelectChannel, loading }) => {
  const latest = summary?.latest_by_channel || [];
  const trendPoints = trendData || [];

  const chartOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['传感器A', '传感器B', '融合值'] },
    grid: { left: 40, right: 16, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trendPoints.map((item) => dayjs(item.sample_time).format('HH:mm:ss')),
    },
    yAxis: { type: 'value', name: '液位(mm)' },
    series: [
      {
        name: '传感器A',
        type: 'line',
        smooth: true,
        data: trendPoints.map((item) => item.value_a),
        lineStyle: { width: 2, color: '#13c2c2', type: 'dashed' },
        symbol: 'none',
      },
      {
        name: '传感器B',
        type: 'line',
        smooth: true,
        data: trendPoints.map((item) => item.value_b),
        lineStyle: { width: 2, color: '#722ed1', type: 'dashed' },
        symbol: 'none',
      },
      {
        name: '融合值',
        type: 'line',
        smooth: true,
        data: trendPoints.map((item) => item.fused_value),
        areaStyle: {
          color: 'rgba(24, 144, 255, 0.18)',
        },
        lineStyle: { width: 3, color: '#1677ff' },
        symbol: 'none',
      },
    ],
  };

  const columns = [
    {
      title: '通道',
      dataIndex: 'channel_name',
      key: 'channel_name',
      render: (name, record) => (
        <a onClick={() => onSelectChannel(record.channel_id)}>{name}</a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'latest_status',
      key: 'latest_status',
      render: (value) =>
        value ? <Tag color={statusColorMap[value]}>{value.toUpperCase()}</Tag> : <Tag>无数据</Tag>,
    },
    {
      title: '传感器A(mm)',
      dataIndex: 'latest_value_a',
      key: 'latest_value_a',
      render: (value) => (value !== null && value !== undefined ? value.toFixed(2) : '-'),
    },
    {
      title: '传感器B(mm)',
      dataIndex: 'latest_value_b',
      key: 'latest_value_b',
      render: (value) => (value !== null && value !== undefined ? value.toFixed(2) : '-'),
    },
    {
      title: '融合值(mm)',
      dataIndex: 'latest_value',
      key: 'latest_value',
      render: (value) => (value === null || value === undefined ? '--' : <strong>{value.toFixed(2)}</strong>),
    },
    {
      title: '采样时间',
      dataIndex: 'latest_time',
      key: 'latest_time',
      render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--'),
    },
  ];

  return (
    <PageShell title="实时监控总览" loading={loading}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Statistic title="通道总数" value={summary?.total_channels || 0} />
        </Col>
        <Col xs={12} md={6}>
          <Statistic title="在线通道" value={summary?.active_channels || 0} />
        </Col>
        <Col xs={12} md={6}>
          <Statistic title="采样总条数" value={summary?.total_samples || 0} />
        </Col>
        <Col xs={12} md={6}>
          <Statistic title="未处理报警" value={summary?.unresolved_alarms || 0} />
        </Col>
      </Row>

      <div className="section-gap">
        <h3 className="section-title">最新通道状态</h3>
        <Table rowKey="channel_id" columns={columns} dataSource={latest} pagination={false} size="middle" />
      </div>

      <div className="section-gap">
        <h3 className="section-title">通道趋势图 {selectedChannelId ? `(通道 ID: ${selectedChannelId})` : ''}</h3>
        {trendPoints.length > 0 ? (
          <ReactECharts option={chartOption} style={{ height: 320 }} />
        ) : (
          <Empty description="暂无趋势数据" />
        )}
      </div>
    </PageShell>
  );
};

export default DashboardPage;
