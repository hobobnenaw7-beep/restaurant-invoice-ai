import { useAuth } from '@/contexts/AuthContext';
import { Beef } from 'lucide-react';
import ExpenseHeader from './ExpenseHeader';
import { RawMaterialsTab } from '@/pages/ExpensesPage';

export default function RawMaterialsPage() {
  const { api } = useAuth();
  return (
    <div className="space-y-6 max-w-[1400px]" data-testid="raw-materials-page">
      <ExpenseHeader
        theme="teal"
        icon={Beef}
        title="Raw Materials"
        subtitle="Ingredients, produce, proteins, and supplier invoices."
        testId="rm-header"
      />
      <RawMaterialsTab api={api} />
    </div>
  );
}
