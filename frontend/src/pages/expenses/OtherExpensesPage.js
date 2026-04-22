import { useAuth } from '@/contexts/AuthContext';
import { Wrench } from 'lucide-react';
import ExpenseHeader from './ExpenseHeader';
import { OtherExpensesTab } from '@/pages/ExpensesPage';

export default function OtherExpensesPage() {
  const { api } = useAuth();
  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="other-expenses-page">
      <ExpenseHeader
        theme="amber"
        icon={Wrench}
        title="Other Expenses"
        subtitle="Utilities, maintenance, subscriptions, and miscellaneous."
        testId="oe-header"
      />
      <OtherExpensesTab api={api} />
    </div>
  );
}
