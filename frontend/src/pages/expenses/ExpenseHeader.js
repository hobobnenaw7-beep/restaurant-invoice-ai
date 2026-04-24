/**
 * ExpenseHeader — shared header strip for each dedicated Expenses sub-page.
 * Provides breadcrumb, color-accented title, icon badge, and a colored
 * underline strip. Consumer pages only need to render the tab body below.
 */
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

// Tailwind safelist (keep classes static so purge doesn't drop them):
const THEMES = {
  teal: {
    ring: 'bg-teal-50 border-teal-200 text-teal-700',
    iconWrap: 'bg-teal-600',
    title: 'text-teal-700',
    accent: 'bg-teal-500',
  },
  blue: {
    ring: 'bg-blue-50 border-blue-200 text-blue-700',
    iconWrap: 'bg-blue-600',
    title: 'text-blue-700',
    accent: 'bg-blue-500',
  },
  amber: {
    ring: 'bg-amber-50 border-amber-200 text-amber-700',
    iconWrap: 'bg-amber-600',
    title: 'text-amber-700',
    accent: 'bg-amber-500',
  },
};

export default function ExpenseHeader({ theme = 'teal', icon: Icon, title, subtitle, testId }) {
  const cfg = THEMES[theme] || THEMES.teal;
  return (
    <div className="space-y-2" data-testid={testId}>
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 text-[11px] text-slate-500" data-testid={`${testId}-breadcrumb`}>
        <Link to="/expenses/raw-materials" className="hover:text-navy-900 transition-colors">Expenses</Link>
        <ChevronRight className="w-3 h-3 text-slate-300" />
        <span className={`font-semibold ${cfg.title}`}>{title}</span>
      </div>

      {/* Title row */}
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-lg ${cfg.iconWrap} flex items-center justify-center flex-shrink-0 shadow-sm`}>
          <Icon className="w-4.5 h-4.5 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className={`font-heading text-xl sm:text-2xl font-extrabold tracking-tight ${cfg.title}`}>
            {title}
          </h1>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>

      {/* Accent strip */}
      <div className={`h-[3px] w-14 rounded-full ${cfg.accent}`} />
    </div>
  );
}
