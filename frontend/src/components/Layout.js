import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  LayoutDashboard, ShoppingCart, DollarSign, Users,
  Package, FileText, MessageCircle, Settings, Bell, Menu, LogOut, ChefHat
} from 'lucide-react';

const mainNav = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/purchases', label: 'Purchases', icon: ShoppingCart },
  { path: '/sales', label: 'Sales', icon: DollarSign },
  { path: '/suppliers', label: 'Suppliers', icon: Users },
  { path: '/items', label: 'Items', icon: Package },
  { path: '/reports', label: 'Reports', icon: FileText },
  { path: '/chat', label: 'Chat Assistant', icon: MessageCircle },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const NavLink = ({ item }) => {
    const isActive = location.pathname === item.path;
    return (
      <Link
        to={item.path}
        onClick={() => setMobileOpen(false)}
        data-testid={`nav-${item.path.slice(1)}`}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
          isActive
            ? 'bg-teal-600/15 text-teal-400'
            : 'text-navy-400 hover:text-white hover:bg-navy-800/60'
        }`}
      >
        <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
        <span>{item.label}</span>
      </Link>
    );
  };

  const SidebarContent = () => (
    <div className="flex flex-col h-full bg-navy-950 text-white" data-testid="sidebar">
      {/* Logo */}
      <div className="p-5 border-b border-navy-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-teal-600 flex items-center justify-center flex-shrink-0">
            <ChefHat className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-heading font-bold text-sm tracking-tight leading-tight">Restaurant</h1>
            <p className="text-[11px] text-navy-400 font-medium">Accountant AI</p>
          </div>
        </div>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {mainNav.map(item => <NavLink key={item.path} item={item} />)}
      </nav>

      {/* Settings + User — pinned at bottom */}
      <div className="border-t border-navy-800">
        <div className="px-3 pt-3 pb-1">
          <NavLink item={{ path: '/settings', label: 'Settings', icon: Settings }} />
        </div>
        <div className="p-4 pt-2">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center text-xs font-bold flex-shrink-0">
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name || 'User'}</p>
              <p className="text-[11px] text-navy-400 truncate">{user?.restaurant_name || ''}</p>
            </div>
          </div>
          <Button
            onClick={logout}
            variant="ghost"
            className="w-full justify-start text-navy-400 hover:text-white hover:bg-navy-800/60 h-8 text-xs"
            data-testid="logout-btn"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Log out
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-50/80">
      <aside className="hidden lg:flex w-64 flex-shrink-0 border-r border-navy-800">
        <div className="w-full">
          <SidebarContent />
        </div>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="p-0 w-64 bg-navy-950 border-none">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 flex items-center justify-between px-4 lg:px-6 glass-header border-b border-slate-200/50 sticky top-0 z-10" data-testid="top-header">
          <button
            onClick={() => setMobileOpen(true)}
            className="lg:hidden p-2 rounded-md hover:bg-slate-100 transition-colors"
            data-testid="mobile-menu-btn"
          >
            <Menu className="w-5 h-5 text-slate-600" />
          </button>
          <div className="flex-1" />
          <Button variant="ghost" size="icon" className="relative" data-testid="notifications-btn">
            <Bell className="w-[18px] h-[18px] text-slate-500" />
            <Badge className="absolute -top-0.5 -right-0.5 h-4 w-4 p-0 flex items-center justify-center text-[10px] bg-red-500 text-white border-0">3</Badge>
          </Button>
        </header>

        <div className="flex-1 overflow-auto p-5 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
