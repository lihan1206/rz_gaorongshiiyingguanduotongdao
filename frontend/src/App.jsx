import {
  Alert,
  Button,
  ConfigProvider,
  Layout,
  Menu,
  Space,
  Spin,
  Typography,
  message,
} from 'antd';
import {
  AlertOutlined,
  AreaChartOutlined,
  DatabaseOutlined,
  LogoutOutlined,
  SettingOutlined,
  TableOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { api } from './api/client';
import ErrorBoundary from './components/ErrorBoundary';
import AlarmsPage from './pages/AlarmsPage';
import ChannelsPage from './pages/ChannelsPage';
import DashboardPage from './pages/DashboardPage';
import HistoryPage from './pages/HistoryPage';
import LoginPage from './pages/LoginPage';
import SamplingPage from './pages/SamplingPage';

const { Header, Content, Sider } = Layout;
const { Title, Text } = Typography;

const AUTH_KEY = 'quartz_monitor_user';

const menuItems = [
  { key: 'dashboard', icon: <AreaChartOutlined />, label: '实时总览' },
  { key: 'channels', icon: <SettingOutlined />, label: '通道管理' },
  { key: 'sampling', icon: <DatabaseOutlined />, label: '同步采样' },
  { key: 'alarms', icon: <AlertOutlined />, label: '报警中心' },
  { key: 'history', icon: <TableOutlined />, label: '历史报表' },
];

const getStoredUser = () => {
  const raw = window.localStorage.getItem(AUTH_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState(null);
  const [channels, setChannels] = useState([]);
  const [alarms, setAlarms] = useState([]);
  const [selectedChannelId, setSelectedChannelId] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [currentUser, setCurrentUser] = useState(getStoredUser);

  const fetchTrendData = useCallback(async (channelId) => {
    if (!channelId) {
      setTrendData([]);
      return;
    }

    try {
      const data = await api.listSamples({ channel_id: channelId, limit: 120 });
      setTrendData(data);
    } catch (err) {
      setTrendData([]);
      message.error(err.message || '趋势数据获取失败');
    }
  }, []);

  const fetchBaseData = useCallback(async () => {
    if (!currentUser) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError('');
      const [summaryRes, channelsRes, alarmsRes] = await Promise.all([
        api.getSummary(),
        api.listChannels(),
        api.listAlarms({ resolved: false }),
      ]);
      setSummary(summaryRes);
      setChannels(channelsRes);
      setAlarms(alarmsRes);

      const nextChannelId = selectedChannelId || summaryRes?.latest_by_channel?.[0]?.channel_id || null;
      setSelectedChannelId(nextChannelId);
      await fetchTrendData(nextChannelId);
    } catch (err) {
      setError(err.message || '系统数据加载失败');
    } finally {
      setLoading(false);
    }
  }, [currentUser, fetchTrendData, selectedChannelId]);

  useEffect(() => {
    fetchBaseData();
  }, [fetchBaseData]);

  useEffect(() => {
    if (!currentUser) {
      return undefined;
    }

    const timer = setInterval(() => {
      fetchBaseData();
    }, 30000);
    return () => clearInterval(timer);
  }, [currentUser, fetchBaseData]);

  const onSelectChannel = async (channelId) => {
    setSelectedChannelId(channelId);
    await fetchTrendData(channelId);
  };

  const handleLogin = async (values) => {
    try {
      setLoginLoading(true);
      const data = await api.login(values);
      window.localStorage.setItem(AUTH_KEY, JSON.stringify(data.user));
      setCurrentUser(data.user);
      setError('');
      message.success('登录成功');
    } catch (err) {
      message.error(err.message || '登录失败');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    window.localStorage.removeItem(AUTH_KEY);
    setCurrentUser(null);
    setSummary(null);
    setChannels([]);
    setAlarms([]);
    setTrendData([]);
    setSelectedChannelId(null);
    setActiveTab('dashboard');
    message.success('已退出登录');
  };

  const pageNode = useMemo(() => {
    if (activeTab === 'dashboard') {
      return (
        <DashboardPage
          summary={summary}
          trendData={trendData}
          selectedChannelId={selectedChannelId}
          onSelectChannel={onSelectChannel}
          loading={loading}
        />
      );
    }

    if (activeTab === 'channels') {
      return <ChannelsPage channels={channels} loading={loading} onRefresh={fetchBaseData} />;
    }

    if (activeTab === 'sampling') {
      return <SamplingPage channels={channels} loading={loading} onAfterSync={fetchBaseData} />;
    }

    if (activeTab === 'alarms') {
      return <AlarmsPage alarms={alarms} loading={loading} onRefresh={fetchBaseData} />;
    }

    return <HistoryPage channels={channels} loading={loading} />;
  }, [activeTab, alarms, channels, fetchBaseData, loading, selectedChannelId, summary, trendData]);

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#006d75',
          borderRadius: 12,
          fontFamily: 'Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif',
        },
      }}
    >
      <ErrorBoundary>
        {!currentUser ? (
          <LoginPage onLogin={handleLogin} loading={loginLoading} />
        ) : (
          <Layout className="app-layout">
            <Sider width={220} breakpoint="lg" collapsedWidth="64" className="left-sider">
              <div className="side-logo">高融石英管多通道液位同步检测系统</div>
              <Menu
                mode="inline"
                selectedKeys={[activeTab]}
                items={menuItems}
                onClick={(event) => setActiveTab(event.key)}
                className="side-menu"
              />
            </Sider>

            <Layout className="content-layout">
              <Header className="app-header">
                <div>
                  <Title className="title" level={4}>
                    高融石英管多通道液位同步检测系统
                  </Title>
                  <Text className="subtitle">工业级多通道监测、报警与历史分析平台</Text>
                </div>
                <Space>
                  <Text className="time-text">{dayjs().format('YYYY-MM-DD HH:mm:ss')}</Text>
                  <Text className="time-text">当前用户：{currentUser.username}</Text>
                  <Button onClick={fetchBaseData}>刷新</Button>
                  <Button icon={<LogoutOutlined />} onClick={handleLogout}>
                    退出登录
                  </Button>
                </Space>
              </Header>

              <Content className="content-wrapper">
                {error && (
                  <Alert
                    className="section-gap"
                    type="error"
                    showIcon
                    message="加载失败"
                    description={error}
                    action={<Button onClick={fetchBaseData}>重试</Button>}
                  />
                )}

                {loading && !summary ? (
                  <div className="loading-box">
                    <Spin size="large" tip="系统数据加载中..." />
                  </div>
                ) : (
                  pageNode
                )}
              </Content>
            </Layout>
          </Layout>
        )}
      </ErrorBoundary>
    </ConfigProvider>
  );
};

export default App;
