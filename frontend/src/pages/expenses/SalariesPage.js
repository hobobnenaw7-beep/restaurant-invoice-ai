import { useAuth } from '@/contexts/AuthContext';
import { Users2 } from 'lucide-react';
import ExpenseHeader from './ExpenseHeader';
import { SalariesTab } from '@/pages/ExpensesPage';

export default function SalariesPage() {
  const { api } = useAuth();
  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="salaries-page">
      <ExpenseHeader
        theme="blue"
        icon={Users2}
        title="Salaries"
        subtitle="Payroll entries for restaurant staff."
        testId="sal-header"
      />
      <SalariesTab api={api} />
    </div>
  );
}
