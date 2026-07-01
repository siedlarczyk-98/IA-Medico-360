import { useMemo, useState } from 'react';
import type { CalculatorListItem } from '../api/calculators';
import { useCalculators } from '../hooks/useCalculators';
import { useToggleFavorite } from '../hooks/useFavorites';
import { CalculatorCard } from '../components/CalculatorCard';
import { useCurrentUser } from '../lib/useCurrentUser';
import { logout } from '../lib/auth';
import { getSpecialtyStyle } from '../lib/specialtyStyles';

export function CalculatorsListPage() {
  const { data: allCalculators, isLoading, error } = useCalculators();
  const user = useCurrentUser();
  const toggleFavorite = useToggleFavorite();
  const [specialtyFilter, setSpecialtyFilter] = useState<'all' | 'favorites' | string>('all');
  const [search, setSearch] = useState('');

  const favoriteCount = useMemo(
    () => (allCalculators ?? []).filter(c => c.is_favorite).length,
    [allCalculators]
  );

  const handleToggleFavorite = (calculator: CalculatorListItem) => {
    toggleFavorite.mutate({ id: calculator.id, slug: calculator.slug, nextValue: !calculator.is_favorite });
  };

  const specialties = useMemo(() => {
    const slugs = new Set((allCalculators ?? []).map(c => c.specialty_slug));
    return Array.from(slugs).sort();
  }, [allCalculators]);

  const specialtyCounts = useMemo(() => {
    const counts = new Map<string, number>();
    (allCalculators ?? []).forEach(c => {
      counts.set(c.specialty_slug, (counts.get(c.specialty_slug) ?? 0) + 1);
    });
    return counts;
  }, [allCalculators]);

  const initials = user?.firstName
    ? user.firstName.slice(0, 2).toUpperCase()
    : (user?.email ?? '?').slice(0, 2).toUpperCase();

  const calculators = useMemo(() => {
    if (!allCalculators) return allCalculators;
    let result = allCalculators;
    if (specialtyFilter === 'favorites') {
      result = result.filter(c => c.is_favorite);
    } else if (specialtyFilter !== 'all') {
      result = result.filter(c => c.specialty_slug === specialtyFilter);
    }
    const query = search.trim().toLowerCase();
    if (query) {
      result = result.filter(c =>
        c.name.toLowerCase().includes(query) ||
        (c.description ?? '').toLowerCase().includes(query)
      );
    }
    return result;
  }, [allCalculators, specialtyFilter, search]);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--fill2)' }}>
      {/* Topbar */}
      <div style={{
        background: '#fff',
        borderBottom: '1px solid var(--line)',
        boxShadow: '0 2px 10px rgba(1,71,81,0.06)',
        padding: '0 24px',
        height: 56,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: 'var(--mint)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M9 12l2 2 4-4m-5-7H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V9l-5-5z" stroke="var(--petrol)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Calculadoras Clínicas</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 26,
                height: 26,
                borderRadius: '50%',
                background: 'var(--petrol)',
                color: '#fff',
                fontSize: 11,
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}>
                {initials}
              </div>
              <span style={{ fontSize: 12, color: 'var(--pen2)' }}>
                {user.firstName ?? user.email}
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={logout}
            style={{
              fontSize: 12,
              color: 'var(--pen3)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 8px',
            }}
          >
            Sair
          </button>
        </div>
      </div>

      {/* Conteúdo */}
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 28 }}>
          <div style={{ width: 4, height: 30, borderRadius: 2, background: 'var(--petrol)' }} />
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--ink)', marginBottom: 4 }}>
              Calculadoras
            </h1>
            <p style={{ fontSize: 13, color: 'var(--pen2)' }}>
              Ferramentas de apoio à decisão clínica baseadas em diretrizes.
            </p>
          </div>
        </div>

        {/* Busca */}
        <div style={{ position: 'relative', marginBottom: 16 }}>
          <span style={{
            position: 'absolute',
            left: 14,
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--pen3)',
            pointerEvents: 'none',
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
              <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar calculadora (ex: CURB-65)..."
            style={{
              width: '100%',
              padding: '11px 14px 11px 40px',
              borderRadius: 12,
              border: '1px solid var(--line)',
              background: '#fff',
              fontSize: 13,
              color: 'var(--ink)',
              outline: 'none',
            }}
            onFocus={e => { e.currentTarget.style.borderColor = 'var(--petrol)'; }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--line)'; }}
          />
        </div>

        {/* Filtros */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            onClick={() => setSpecialtyFilter(prev => prev === 'favorites' ? 'all' : 'favorites')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '8px 14px',
              borderRadius: 20,
              border: '1px solid #f5a623',
              background: specialtyFilter === 'favorites' ? '#f5a623' : 'none',
              color: specialtyFilter === 'favorites' ? '#fff' : '#f5a623',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill={specialtyFilter === 'favorites' ? '#fff' : '#f5a623'}>
              <path d="M12 2.5l2.9 6.3 6.9.7-5.2 4.7 1.5 6.8L12 17.6l-6.1 3.4 1.5-6.8-5.2-4.7 6.9-.7L12 2.5z" />
            </svg>
            Favoritas ({favoriteCount})
          </button>

          <div style={{ position: 'relative' }}>
            <select
              value={specialtyFilter === 'favorites' ? 'all' : specialtyFilter}
              onChange={e => setSpecialtyFilter(e.target.value)}
              style={{
                appearance: 'none',
                WebkitAppearance: 'none',
                padding: '8px 34px 8px 14px',
                borderRadius: 20,
                border: '1px solid var(--line)',
                background: '#fff',
                color: 'var(--ink)',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              <option value="all">Todas as especialidades ({allCalculators?.length ?? 0})</option>
              {specialties.map(slug => {
                const style = getSpecialtyStyle(slug);
                return (
                  <option key={slug} value={slug}>
                    {style.label} ({specialtyCounts.get(slug) ?? 0})
                  </option>
                );
              })}
            </select>
            <span style={{
              position: 'absolute',
              right: 14,
              top: '50%',
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
              color: 'var(--pen2)',
              fontSize: 10,
            }}>
              ▾
            </span>
          </div>
        </div>

        {isLoading && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ height: 110, borderRadius: 14, background: 'var(--fill)', animation: 'pulse 1.4s ease-in-out infinite' }} />
            ))}
          </div>
        )}

        {error && (
          <p style={{ fontSize: 13, color: 'var(--red)', background: 'var(--red-bg)', padding: '12px 14px', borderRadius: 10 }}>
            Erro ao carregar calculadoras: {error instanceof Error ? error.message : 'Tente novamente.'}
          </p>
        )}

        {calculators && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
            {calculators.map(c => (
              <CalculatorCard
                key={c.id}
                calculator={c}
                onToggleFavorite={handleToggleFavorite}
              />
            ))}
            {calculators.length === 0 && (
              <p style={{ fontSize: 13, color: 'var(--pen2)', textAlign: 'center', padding: 40, gridColumn: '1 / -1' }}>
                {specialtyFilter === 'favorites'
                  ? 'Nenhuma calculadora favoritada ainda. Clique na estrela de um card para adicioná-la aqui.'
                  : 'Nenhuma calculadora encontrada.'}
              </p>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
      `}</style>
    </div>
  );
}
