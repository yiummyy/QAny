import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSettings, updateSettings } from "../../../api/admin";
import { QUERY_KEYS } from "../../../lib/constants";
import LoadingSpinner from "../../common/LoadingSpinner";
import ErrorBanner from "../../common/ErrorBanner";
import { toast } from "../../common/Toast";
import { ApiError } from "../../../api/client";

function isMasked(val: unknown): boolean {
  return typeof val === "string" && val.includes("****");
}

interface ApiKeyFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
}

function ApiKeyField({ label, value, onChange }: ApiKeyFieldProps) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);

  const displayValue = editing ? "" : show && !isMasked(value) ? value : isMasked(value) ? value : value ? "****" + value.slice(-4) : "";
  const placeholder = isMasked(value) ? "输入新密钥以覆盖" : "输入 API Key";

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      <div className="mt-1 flex items-center gap-1">
        <input
          type={show && !isMasked(displayValue) ? "text" : "password"}
          value={editing ? "" : displayValue}
          placeholder={placeholder}
          onChange={(e) => {
            setEditing(true);
            if (e.target.value === "") onChange("");
            else onChange(e.target.value);
          }}
          onFocus={() => {
            if (isMasked(value)) {
              setEditing(true);
            }
          }}
          onBlur={() => setEditing(false)}
          className="w-full rounded border px-2 py-1 text-sm font-mono focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="shrink-0 rounded border px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
        >
          {show ? "隐藏" : "显示"}
        </button>
      </div>
    </div>
  );
}

function ModelConfigSection({
  title,
  desc,
  config,
  update,
  prefix,
}: {
  title: string;
  desc?: string;
  config: any;
  update: (k: string, v: any) => void;
  prefix?: string;
}) {
  const get = (k: string) => {
    if (prefix) {
      const routing = config?.model_routing || {};
      const stageConfig = routing[prefix];
      if (typeof stageConfig === "string") {
        if (k === "model") return stageConfig;
        return "";
      }
      return stageConfig?.[k] ?? "";
    }
    return config[`llm_${k}`] ?? "";
  };

  const set = (k: string, v: string) => {
    if (prefix) {
      const routing = config.model_routing || {};
      let stageConfig = routing[prefix] || {};
      if (typeof stageConfig === "string") {
        stageConfig = { model: stageConfig };
      }
      update("model_routing", {
        ...routing,
        [prefix]: { ...stageConfig, [k]: v },
      });
    } else {
      update(`llm_${k}`, v);
    }
  };

  const provider = get("provider") || (prefix ? "" : "dashscope");

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-5 shadow-sm">
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      {desc && <p className="mt-1 mb-4 text-xs text-gray-500">{desc}</p>}
      
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-gray-700">模型应用厂商</label>
          <select
            value={provider}
            onChange={(e) => set("provider", e.target.value)}
            className="mt-1 block w-full rounded border bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {prefix && <option value="">(继承全局配置)</option>}
            <option value="dashscope">通义千问 (DashScope)</option>
            <option value="deepseek">DeepSeek</option>
            <option value="zhipu">智谱 AI</option>
            <option value="openai">OpenAI (或其他兼容接口)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">模型名 (Model Name)</label>
          <input
            type="text"
            value={get("model")}
            placeholder={prefix ? "(继承全局配置)" : "例如: qwen-plus"}
            onChange={(e) => set("model", e.target.value)}
            className="mt-1 w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-gray-700">Base URL (接口地址)</label>
          <input
            type="text"
            value={get("base_url")}
            placeholder={
              prefix && !provider
                ? "(继承全局配置)"
                : provider === "openai"
                ? "https://api.openai.com/v1"
                : provider === "deepseek"
                ? "https://api.deepseek.com/v1"
                : provider === "zhipu"
                ? "https://open.bigmodel.cn/api/paas/v4"
                : "https://dashscope.aliyuncs.com/compatible-mode/v1"
            }
            onChange={(e) => set("base_url", e.target.value)}
            className="mt-1 w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="sm:col-span-2">
          <ApiKeyField
            label="API Key"
            value={get("api_key")}
            onChange={(v) => set("api_key", v)}
          />
        </div>
      </div>
    </div>
  );
}

export default function SettingsForm() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"system" | "model">("system");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUERY_KEYS.admin.settings,
    queryFn: getSettings,
  });

  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (data && !initialized) {
      setConfig({ ...(data.config as Record<string, unknown>) });
      setInitialized(true);
    }
  }, [data, initialized]);

  const mut = useMutation({
    mutationFn: updateSettings,
    onSuccess: (newData) => {
      queryClient.setQueryData(QUERY_KEYS.admin.settings, newData);
      toast("配置已保存", "success");
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === 40001) {
        toast("配置已被其他管理员修改，请刷新后重试", "error");
        refetch();
        setInitialized(false);
      } else {
        toast("保存失败", "error");
      }
    },
  });

  function handleSave() {
    if (!data) return;
    mut.mutate({ config, updated_at: data.updated_at });
  }

  function update(key: string, value: unknown) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message="加载配置失败" onRetry={() => refetch()} />;
  if (!data) return null;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab("system")}
            className={`${
              activeTab === "system"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
            } whitespace-nowrap border-b-2 px-1 pb-4 text-sm font-medium`}
          >
            系统配置
          </button>
          <button
            onClick={() => setActiveTab("model")}
            className={`${
              activeTab === "model"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
            } whitespace-nowrap border-b-2 px-1 pb-4 text-sm font-medium`}
          >
            大模型配置
          </button>
        </nav>
      </div>

      {activeTab === "system" && (
        <div className="max-w-xl space-y-5">
          <div>
            <label className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-700">Rerank 开关</span>
              <button
                onClick={() => update("rerank_enabled", !config.rerank_enabled)}
                className={`relative inline-flex h-6 w-11 rounded-full transition-colors ${
                  config.rerank_enabled ? "bg-blue-600" : "bg-gray-300"
                }`}
                role="switch"
                aria-checked={!!config.rerank_enabled}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform mt-0.5 ${
                    config.rerank_enabled ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </label>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              幻觉检测阈值
              <span className="ml-2 text-xs text-gray-400">
                {String(config.hallucination_threshold ?? 0.6)}
              </span>
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={Number(config.hallucination_threshold ?? 0.6)}
              onChange={(e) => update("hallucination_threshold", parseFloat(e.target.value))}
              className="mt-1 w-full"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">最大上下文文档数</label>
            <input
              type="number"
              value={Number(config.max_context_docs ?? 5)}
              onChange={(e) =>
                update("max_context_docs", Math.max(1, parseInt(e.target.value) || 5))
              }
              className="mt-1 w-24 rounded border px-2 py-1 text-sm"
              min={1}
              max={20}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">单日成本上限 (RMB)</label>
            <input
              type="number"
              value={Number(config.cost_daily_limit_rmb ?? 1000)}
              onChange={(e) =>
                update("cost_daily_limit_rmb", Math.max(0, parseFloat(e.target.value) || 0))
              }
              className="mt-1 w-36 rounded border px-2 py-1 text-sm"
              min={0}
              step={10}
            />
          </div>
        </div>
      )}

      {activeTab === "model" && (
        <div className="space-y-6">
          <ModelConfigSection
            title="全局默认模型"
            desc="当各个环节未单独配置时，将默认使用此配置进行调用。"
            config={config}
            update={update}
          />

          <ModelConfigSection
            title="Agent 规划 (Plan)"
            desc="负责每一步的工具选择（tool_call / final_answer）与多步决策。建议使用逻辑推理强的小模型（如 qwen-turbo / deepseek-v4-flash），低温度 (0.1)。"
            config={config}
            update={update}
            prefix="plan"
          />

          <ModelConfigSection
            title="意图识别 (Intent Recognition)"
            desc="负责多轮指代消解、意图分类、实体抽取。建议使用速度快的轻量模型（如 qwen-turbo），一次调用完成改写+分类+抽取。"
            config={config}
            update={update}
            prefix="intent_recognition"
          />

          <ModelConfigSection
            title="答案生成 (Answer Generation)"
            desc="基于检索片段流式生成最终答案，直接影响用户看到的回答质量。建议使用能力最强的大模型（如 qwen-plus / deepseek-chat），中等温度 (0.3)。"
            config={config}
            update={update}
            prefix="answer_generation"
          />

          <ModelConfigSection
            title="幻觉检测 (Hallucination Check)"
            desc="逐句验证生成的答案与来源文档的事实一致性。建议使用逻辑判断较强的模型（如 qwen-turbo）。"
            config={config}
            update={update}
            prefix="hallucination_check"
          />

          <ModelConfigSection
            title="上下文压缩 (Context Compaction)"
            desc="在多轮对话超过 token 阈值时，将历史对话压缩为结构化摘要。仅在长对话时触发，建议使用速度快的小模型（如 qwen-turbo），输出 token 上限 300。"
            config={config}
            update={update}
            prefix="compaction"
          />

          <ModelConfigSection
            title="图片描述 (Image Description)"
            desc="将文档中的图片/图表/截图转换为文字描述，使图片内容可被检索。仅在启用视觉识别 (VISION_ENABLED=true) 时调用，建议使用多模态模型（如 qwen-vl-max）。"
            config={config}
            update={update}
            prefix="image_description"
          />
        </div>
      )}

      <div className="pt-4 border-t border-gray-200">
        <button
          onClick={handleSave}
          disabled={mut.isPending}
          className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
        >
          {mut.isPending ? "保存中..." : "保存配置"}
        </button>
      </div>
    </div>
  );
}
