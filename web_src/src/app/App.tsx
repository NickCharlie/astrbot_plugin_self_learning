import { Match, Switch } from 'solid-js';
import { DashboardProvider, useDashboard } from '../stores/dashboard';
import { AppShell } from '../components/layout/AppShell';
import { ConfirmDialog, ToastViewport } from '../components/feedback/Feedback';
import { HomePage } from '../pages/home/HomePage';
import { OverviewPage } from '../pages/overview/OverviewPage';
import { InsightsPage } from '../pages/insights/InsightsPage';
import { MonitoringPage } from '../pages/monitoring/MonitoringPage';
import { ReviewsPage } from '../pages/reviews/ReviewsPage';
import { JargonLearningPage } from '../pages/jargon-learning/JargonLearningPage';
import { ExpressionLearningPage } from '../pages/expression-learning/ExpressionLearningPage';
import { PersonaLearningPage } from '../pages/persona-learning/PersonaLearningPage';
import { ContentPage } from '../pages/content/ContentPage';
import { GraphsPage } from '../pages/graphs/GraphsPage';
import { ReplyStrategyPage } from '../pages/reply-strategy/ReplyStrategyPage';
import { IntegrationsPage } from '../pages/integrations/IntegrationsPage';
import { SettingsPage } from '../pages/settings/SettingsPage';
import { ShadowModePage } from '../pages/shadow-mode/ShadowModePage';

function DashboardRoutes() {
  const dashboard = useDashboard();
  return (
    <AppShell>
      <Switch fallback={<HomePage />}>
        <Match when={dashboard.page() === 'home'}><HomePage /></Match>
        <Match when={dashboard.page() === 'overview'}><OverviewPage /></Match>
        <Match when={dashboard.page() === 'insights'}><InsightsPage /></Match>
        <Match when={dashboard.page() === 'monitoring'}><MonitoringPage /></Match>
        <Match when={dashboard.page() === 'reviews'}><ReviewsPage /></Match>
        <Match when={dashboard.page() === 'jargon-learning'}><JargonLearningPage /></Match>
        <Match when={dashboard.page() === 'expression-learning'}><ExpressionLearningPage /></Match>
        <Match when={dashboard.page() === 'persona-learning'}><PersonaLearningPage /></Match>
        <Match when={dashboard.page() === 'shadow-mode'}><ShadowModePage /></Match>
        <Match when={dashboard.page() === 'content'}><ContentPage /></Match>
        <Match when={dashboard.page() === 'graphs'}><GraphsPage /></Match>
        <Match when={dashboard.page() === 'reply-strategy'}><ReplyStrategyPage /></Match>
        <Match when={dashboard.page() === 'integrations'}><IntegrationsPage /></Match>
        <Match when={dashboard.page() === 'settings'}><SettingsPage /></Match>
      </Switch>
      <ToastViewport />
      <ConfirmDialog />
    </AppShell>
  );
}

export function App() {
  return <DashboardProvider><DashboardRoutes /></DashboardProvider>;
}
