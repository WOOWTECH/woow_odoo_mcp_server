import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, Loader2, Wrench, ToggleLeft, ToggleRight, RefreshCw } from 'lucide-react';
import { apiGet, apiPut } from '../api';

export default function ToolManager() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [pendingToggles, setPendingToggles] = useState({});

  const { data: toolsData, isLoading, error, refetch } = useQuery({
    queryKey: ['tools'],
    queryFn: () => apiGet('/tools'),
  });

  const mutation = useMutation({
    mutationFn: (tools) => apiPut('/tools', { tools }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] });
      setPendingToggles({});
    },
    onError: () => {
      setPendingToggles({});
    },
  });

  const tools = toolsData?.tools || [];

  const filteredTools = useMemo(() => {
    if (!search.trim()) return tools;
    const q = search.toLowerCase();
    return tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
    );
  }, [tools, search]);

  const categories = useMemo(() => {
    const grouped = {};
    for (const tool of filteredTools) {
      const cat = tool.category || 'Uncategorized';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(tool);
    }
    return Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredTools]);

  function handleToggle(toolName, currentEnabled) {
    const newEnabled = !currentEnabled;
    setPendingToggles((prev) => ({ ...prev, [toolName]: true }));

    const updatedTools = tools.map((t) =>
      t.name === toolName ? { ...t, enabled: newEnabled } : t
    );

    mutation.mutate(updatedTools);
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-gray-500" size={24} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center">
        <p className="text-red-400 font-medium">Failed to load tools</p>
        <p className="text-red-400/70 text-sm mt-1">{error.message}</p>
        <button
          onClick={() => refetch()}
          className="mt-4 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  const enabledCount = tools.filter((t) => t.enabled).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">Tool Manager</h2>
          <p className="text-sm text-gray-500 mt-1">
            {enabledCount} of {tools.length} tools enabled
          </p>
        </div>
        {mutation.isPending && (
          <div className="flex items-center gap-2 px-3 py-2 bg-brand-600/20 border border-brand-600/30 rounded-lg text-sm text-brand-400">
            <Loader2 size={14} className="animate-spin" />
            <span>Applying...</span>
          </div>
        )}
      </div>

      <div className="relative mb-6">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search tools by name, description, or category..."
          className="w-full pl-10 pr-4 py-2.5 bg-gray-900 border border-gray-800 rounded-lg text-gray-200 placeholder-gray-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-colors"
        />
      </div>

      {categories.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Wrench size={32} className="mx-auto mb-3 opacity-50" />
          <p>No tools match your search</p>
        </div>
      ) : (
        <div className="space-y-6">
          {categories.map(([category, categoryTools]) => (
            <div key={category}>
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 px-1">
                {category}
                <span className="ml-2 text-gray-600 font-normal">({categoryTools.length})</span>
              </h3>
              <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
                {categoryTools.map((tool) => {
                  const isPending = pendingToggles[tool.name];
                  return (
                    <div
                      key={tool.name}
                      className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0 mr-4">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-200 font-mono">
                            {tool.name}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="text-xs text-gray-500 mt-0.5 truncate">
                            {tool.description}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => handleToggle(tool.name, tool.enabled)}
                        disabled={isPending || mutation.isPending}
                        className="shrink-0 disabled:opacity-50 transition-opacity"
                        title={tool.enabled ? 'Disable tool' : 'Enable tool'}
                      >
                        {isPending ? (
                          <Loader2 size={24} className="animate-spin text-gray-500" />
                        ) : tool.enabled ? (
                          <ToggleRight size={28} className="text-brand-500" />
                        ) : (
                          <ToggleLeft size={28} className="text-gray-600" />
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
