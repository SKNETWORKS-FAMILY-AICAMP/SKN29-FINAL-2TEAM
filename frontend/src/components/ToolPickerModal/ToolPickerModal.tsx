import { useState } from 'react';
import { Badge } from '../Badge/Badge';
import { Button } from '../Button/Button';
import { Checkbox } from '../Checkbox/Checkbox';
import { Icon } from '../Icon/Icon';
import { Modal } from '../Modal/Modal';
import type { BadgeTone } from '../Badge/Badge';
import type { ToolChoice } from '../../api/agents';
import type { McpServer } from '../../api/mcp';
import styles from './ToolPickerModal.module.css';

type Tab = 'builtin' | 'mcp';

const TABS: { id: Tab; label: string }[] = [
  { id: 'builtin', label: '툴 선택' },
  { id: 'mcp', label: '커스텀 도구 선택' },
];

const SERVER_STATUS: Record<McpServer['status'], { tone: BadgeTone; label: string }> = {
  CONNECTED: { tone: 'success', label: '연결됨' },
  UNCHECKED: { tone: 'neutral', label: '미확인' },
  ERROR: { tone: 'warning', label: '연결 실패' },
};

export interface ToolPickerModalProps {
  open: boolean;
  onClose: () => void;
  /** MCP 도구(`mcp:` 접두사)는 빼고 넘긴다 — 이 목록은 「툴 선택」 탭 전용이다. */
  builtinTools: ToolChoice[];
  mcpServers: McpServer[];
  toolRefs: string[];
  onToggle: (ref: string) => void;
  /**
   * 카테고리 카드 헤더의 「전체 선택」 마스터 체크박스. `onToggle`을 여러 번
   * 부르지 않는다 — 부모의 토글 함수가 `toolRefs` 스냅샷을 읽어 하나씩
   * 계산하는 구조라, 연달아 부르면 뒤 호출이 앞 호출을 덮어써 마지막 도구만
   * 반영된다. 그룹 전체를 한 번에 계산하는 별도 콜백으로 받는다.
   */
  onToggleGroup: (refs: string[], turnOn: boolean) => void;
  /**
   * 이 대화의 도구 선택을 **고정 기본 집합**(`ToolChoice.is_default === true`)으로
   * 되돌린다. 채팅 「+」에서만 준다 — 에이전트 편집 화면은 원본 자체를 고치는
   * 자리라 되돌릴 대상이 없다. 안 주면 초기화 버튼이 안 뜬다. 지금 선택이 이미
   * 고정 기본 집합과 같으면 버튼은 비활성이다.
   */
  onReset?: () => void;
}

/** 두 문자열 목록이 (순서 무관) 같은 집합인가. */
function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((item) => set.has(item));
}

/** `ToolChoice.category`가 없으면(MCP 등) 이 이름으로 묶는다. */
const UNCATEGORIZED = '기타';

/**
 * 카테고리 카드에 보여줄 한 줄 설명 — 개별 도구 설명과 달리 백엔드에 안
 * 둔다(화면 전용 문구라 도구마다 중복시킬 이유가 없다). 없으면 이름만
 * 보인다(카드 자체는 뜬다).
 */
const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  검색: '팀 문서와 웹에서 필요한 자료를 찾습니다.',
  문서: '문서를 만들거나 파일을 변환·정리합니다.',
  업무: '프로젝트와 플랫폼·Jira 업무를 조회하고 변경합니다.',
  팀: '팀원, 업무량, 부재 정보를 확인합니다.',
  데이터: '표를 가공하고 데이터 품질과 파일 변경점을 확인합니다.',
  계산: '현재 시각, 날짜, 수식과 단위를 계산합니다.',
  [UNCATEGORIZED]: '카테고리가 지정되지 않은 도구입니다.',
};

/**
 * 개별 도구의 **사람용 한 줄 설명**. 백엔드의 `description`은 모델이 도구를
 * 고르라고 쓴 라우팅 지시문이라(다른 도구 이름·명령문·별표까지 들어 있다)
 * 사용자에게 그대로 보이면 안 된다 — 그래서 화면 문구를 여기 따로 둔다.
 * 여기 없는 도구는 이름만 보인다(새 도구를 더하면 여기에 짧게 한 문장 추가).
 */
const TOOL_DESCRIPTIONS: Record<string, string> = {
  document_search: '문서에서 질문과 관련된 문장을 찾아 근거로 보여줍니다.',
  document_list: '팀에 어떤 문서가 있는지 목록으로 보여줍니다. 아직 읽지 않은 파일도 함께 알려줍니다.',
  people_list: '팀원의 이름·직책·기술 스택을 조회합니다.',
  workload_report: '팀원별로 남은 업무 시간을 계산해 보여줍니다.',
  absence_list: '팀원의 휴가 등 부재 일정을 조회합니다.',
  task_extraction: '문서에서 해야 할 일을 찾아 근거 문장과 함께 정리합니다.',
  project_list: '팀의 프로젝트 목록과 진행률을 조회합니다.',
  task_list: '등록된 업무를 조회합니다.',
  task_register: '정리된 업무를 시스템에 등록합니다.',
  task_update: '등록된 업무의 상태와 마감을 고칩니다.',
  web_search: '인터넷에서 정보를 찾아 출처와 함께 알려줍니다.',
  jira_get_issues: 'Jira 이슈를 조회합니다.',
  jira_create_issues: 'Jira 에 새 이슈를 등록합니다.',
  // 2026-08-26. 아래 셋이 이 표에 없어서 모델용 지시문이 그대로 보이고 있었다 —
  // 별표(`**`)와 내부 도구 이름까지 화면에 났다(위 주석이 막으려던 그것이다).
  table_export: '표를 엑셀 파일로 만들어 「내 파일」에 저장합니다.',
  document_create: '글을 워드 파일로 만들어 「내 파일」에 저장합니다.',
  document_sync: '연결된 저장소에서 방금 바뀐 문서를 다시 읽어 옵니다.',
  document_read: '선택한 PDF·Word·Excel 파일의 본문과 표를 읽습니다.',
  document_convert: '파일을 다른 형식으로 변환해 새 파일로 저장합니다.',
  pdf_edit: 'PDF를 병합·분할하거나 페이지 순서와 방향을 바꿉니다.',
  file_inspect: '파일의 실제 형식, 크기, 해시와 작성 정보를 확인합니다.',
  file_sanitize: '파일의 작성자·생성 도구 정보를 제거한 사본을 만듭니다.',
  archive_manage: '여러 파일을 ZIP으로 묶거나 ZIP 파일을 풀어 저장합니다.',
  table_transform: '표를 필터·정렬·결합·집계하고 필요하면 결과 파일로 저장합니다.',
  data_quality_check: '표의 빈 값, 중복, 타입과 스키마 오류를 찾습니다.',
  file_compare: '두 PDF·Word·Excel 파일의 추가·삭제·수정 내역을 비교합니다.',
  calculate: '수식, 단위, 기간, 영업일과 시간대를 계산합니다.',
  get_current_datetime: '오늘 날짜와 요일을 확인합니다.',
  diagram_create: '순서도·시퀀스 같은 다이어그램을 그립니다.',
  chart_create: '값을 막대·꺾은선·파이 차트로 그립니다.',
  graph_create: '노드와 연결로 관계 그래프를 그립니다.',
};

/** 카테고리 등장 순서를 그대로 유지해 그룹으로 묶는다. */
function groupByCategory(items: ToolChoice[]): [string, ToolChoice[]][] {
  const order: string[] = [];
  const byCategory = new Map<string, ToolChoice[]>();
  for (const item of items) {
    const category = item.category ?? UNCATEGORIZED;
    if (!byCategory.has(category)) {
      order.push(category);
      byCategory.set(category, []);
    }
    byCategory.get(category)!.push(item);
  }
  return order.map((category) => [category, byCategory.get(category)!]);
}

/**
 * 도구 선택 팝업 — 기본 제공 도구와 MCP 서버 도구를 탭으로 나눠 고른다.
 *
 * 한 화면에 다 늘어놓으면 MCP 서버가 늘수록(서버마다 도구 여러 개) 목록이
 * 한없이 길어진다. 탭으로 나누면 「지금 뭘 고르고 있는지」가 분명해진다.
 */
export function ToolPickerModal({
  open,
  onClose,
  builtinTools,
  mcpServers,
  toolRefs,
  onToggle,
  onToggleGroup,
  onReset,
}: ToolPickerModalProps) {
  const [tab, setTab] = useState<Tab>('builtin');
  const builtinGroups = groupByCategory(builtinTools);
  /** 「기본값으로 초기화」가 되돌릴 고정 집합과, 지금 선택이 이미 그 집합인지. */
  const defaultRefs = builtinTools.filter((tool) => tool.is_default).map((tool) => tool.tool_ref);
  const builtinRefSet = new Set(builtinTools.map((tool) => tool.tool_ref));
  const atDefault = sameSet(
    toolRefs.filter((ref) => builtinRefSet.has(ref)),
    defaultRefs,
  );
  /** "세부 툴 확인"으로 펼친 카테고리 — 기본은 다 접혀 있다. 먼저 카테고리
   * 단위로만 고르게 하고, 안에 뭐가 있는지는 필요할 때만 보게 한다. */
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  function toggleExpanded(category: string) {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="도구 선택"
      width={640}
      footer={<Button onClick={onClose}>완료</Button>}
    >
      <div className={styles.tabs} role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={[styles.tab, tab === item.id ? styles.tabOn : ''].filter(Boolean).join(' ')}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'builtin' && (
        <div className={styles.serverList}>
          {onReset && (
            <div className={styles.resetRow}>
              <Button size="sm" variant="ghost" disabled={atDefault} onClick={onReset}>
                기본값으로 초기화
              </Button>
            </div>
          )}
          {builtinGroups.map(([category, items]) => {
            const allOn = items.every((toolItem) => toolRefs.includes(toolItem.tool_ref));
            const expanded = expandedCategories.has(category);
            return (
              <div key={category} className={styles.serverGroup}>
                <div className={styles.serverHead}>
                  <span className={styles.serverName}>
                    <Checkbox
                      checked={allOn}
                      onChange={(next) =>
                        onToggleGroup(
                          items.map((toolItem) => toolItem.tool_ref),
                          next,
                        )
                      }
                      label={category}
                    />
                  </span>
                  {CATEGORY_DESCRIPTIONS[category] && (
                    <p className={styles.categoryDesc}>{CATEGORY_DESCRIPTIONS[category]}</p>
                  )}
                </div>

                <button
                  type="button"
                  className={styles.expandToggle}
                  onClick={() => toggleExpanded(category)}
                  aria-expanded={expanded}
                >
                  <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={13} />
                  세부 툴 확인 ({items.length})
                </button>

                {expanded && (
                  <div className={styles.toolList}>
                    {items.map((toolItem) => {
                      const checked = toolRefs.includes(toolItem.tool_ref);
                      return (
                        <div
                          key={toolItem.tool_ref}
                          className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                        >
                          <Checkbox checked={checked} onChange={() => onToggle(toolItem.tool_ref)} />
                          <div className={styles.toolText}>
                            <strong>
                              {toolItem.name}
                              {toolItem.side_effect && <span className={styles.gate}> · 승인 필요</span>}
                            </strong>
                            {TOOL_DESCRIPTIONS[toolItem.tool_ref] && (
                              <span>{TOOL_DESCRIPTIONS[toolItem.tool_ref]}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {builtinTools.length === 0 && <p className={styles.help}>기본 제공 도구가 없습니다.</p>}
        </div>
      )}

      {tab === 'mcp' && (
        <div className={styles.serverList}>
          {mcpServers.length === 0 && <p className={styles.help}>아직 이 팀에 붙어 있는 서버가 없습니다.</p>}
          {mcpServers.map((server) => {
            const chip = SERVER_STATUS[server.status];
            const usable = server.status === 'CONNECTED';
            return (
              <div key={server.mcp_server_id} className={styles.serverGroup}>
                <div className={styles.serverHead}>
                  <span className={styles.serverName}>
                    {server.name}
                    <Badge tone={chip.tone}>{chip.label}</Badge>
                  </span>
                  <span className={styles.help}>{server.endpoint_url}</span>
                </div>
                {!usable && (
                  <p className={styles.help}>
                    {server.status === 'UNCHECKED'
                      ? '설정에서 연결을 확인해야 도구를 고를 수 있습니다.'
                      : '연결이 실패한 서버입니다. 설정에서 연결 상태를 확인하세요.'}
                  </p>
                )}
                {usable && server.tools.length === 0 && (
                  <p className={styles.help}>이 서버는 제공하는 도구가 없습니다.</p>
                )}
                {usable && server.tools.length > 0 && (
                  <div className={styles.toolList}>
                    {server.tools.map((tool) => {
                      const ref = `mcp:${tool.mcp_tool_id}`;
                      const checked = toolRefs.includes(ref);
                      return (
                        <div
                          key={tool.mcp_tool_id}
                          className={[styles.toolRow, checked ? styles.toolRowOn : ''].filter(Boolean).join(' ')}
                        >
                          <Checkbox checked={checked} disabled={!tool.enabled} onChange={() => onToggle(ref)} />
                          <div className={styles.toolText}>
                            <strong>
                              {tool.name}
                              <span className={styles.gate}> · 승인 필요</span>
                            </strong>
                            <span>{tool.description || (tool.enabled ? '' : '사용 중지된 도구입니다.')}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
          {/* 팀이 스스로 서버를 못 붙이므로, 어디로 말하면 되는지 남긴다. */}
          <p className={styles.help}>
            서버 등록은 운영자에게 요청하세요. 주소·키를 다루는 작업이라 운영자가 대신 등록합니다.
          </p>
        </div>
      )}

    </Modal>
  );
}
