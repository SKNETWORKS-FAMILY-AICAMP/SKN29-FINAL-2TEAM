# you asked

message time: 2026-08-25 12:03:04

근데 지금 보면 깃허브상에 그렇게 되어있는거 아닌가? 완전 그대로는 아니더라도 어느정도 프롬프팅이 되어있을텐데, 그게 맞다면 그런 상태임에도 저렇게 나온거잖아.
맞다면 대응책 요청 (분명 방법이 있을 것 같은데)

---

# chatgpt response

맞습니다. **지금 레포 상태를 다시 확인해보면 이미 그 정도가 아니라 꽤 명시적으로 프롬프팅되어 있습니다.**

현재 `services/agent_runtime/prompts.py`에 실제로:

> `생각 과정도 화면에 그대로 보인다. 사용자가 한국어로 물으면 생각 과정과 답변을 모두 한국어로 쓴다.`

라고 들어가 있습니다.  그런데 현재 OpenAI 모델 생성부에서는 별도로 `reasoning={"effort": ..., "summary": "auto"}`를 켜고 있고,  이미지에서는 그 `reasoning.summary`가 영어로 나왔습니다.

즉 **“프롬프트에 한국어로 하라고 적으면 되지 않나?”는 이미 해봤는데 안 된 상태**라고 보는 게 맞습니다.

핵심 원인은 `reasoning.summary`가 일반 Assistant 답변과 성격이 다르기 때문입니다. Responses API의 별도 reasoning item/summary event로 생성되고, 현재 공개 API에는 `reasoning.summary.language = "ko"` 같은 언어 지정 옵션이 없습니다. ([OpenAI Developers](https://developers.openai.com/api/reference/cli/resources/responses/methods/create?utm_source=chatgpt.com))

그래서 대응책은 명확합니다.

### 1순위: 지금 영어가 나오는 자리의 **데이터 원본만 바꾼다**

UI 모양을 굳이 바꿀 필요도 없습니다.

현재:

```text
[생각 과정]

reasoning.summary
↓
**Assessing project tasks**
I need to inspect ...
```

이라면 이것을:

```text
[작업 과정]

user-visible preamble / commentary
↓
현재 진행 중인 프로젝트와 업무 현황을 먼저 확인하겠습니다.
```

로 바꾸는 겁니다.

OpenAI가 현재 공식적으로 지원·권장하는 방식도 이쪽입니다. 최신 모델 가이드에서는 Tool Call 전에 **Preamble이라는 짧은 user-visible 설명**을 출력하게 할 수 있다고 명시하고 있고, 최근 모델에서는 중간 사용자 메시지를 `phase: "commentary"`, 최종 답변을 `phase: "final_answer"`로 구분하는 방식까지 안내하고 있습니다. ([OpenAI Developers](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.2&utm_source=chatgpt.com))

즉 굳이:

```text
영어 Reasoning
→ 한국어 번역
```

하지 않고,

```text
Internal reasoning        ← 사용자에게 안 보여줌

한국어 commentary
"프로젝트 현황을 먼저 확인하겠습니다."
        ↓
project_list Tool
        ↓
한국어 commentary
"확인한 프로젝트를 기준으로 업무를 살펴보겠습니다."
        ↓
task Tool
```

로 만들 수 있습니다.

**추가 API 호출도 필요 없습니다. 같은 Agent 실행에서 나오는 사용자용 출력입니다.**

---

특히 중요한 건, 사용자가 보기에는 지금과 거의 똑같이 만들 수 있다는 겁니다.

지금:

```text
생각 과정 2단계

Assessing project tasks
I need to inspect projects and tasks...

프로젝트 조회 완료
```

을:

```text
작업 과정 2단계

현재 진행 중인 프로젝트와 업무 현황을 먼저 확인하겠습니다.

프로젝트 조회 완료
```

로 바꾸면 됩니다.

그래서 담당자분이 **“그냥 저 영어 나오는 것만 한국어로 못 바꾸냐?”**라고 묻는 거라면,

> **네, 화면은 그대로 두고 그 영역에 넣는 소스를 `reasoning.summary`에서 한국어 Preamble/Commentary로 바꾸면 됩니다.**

가 가장 정확한 답이에요.

---

다만 한 가지는 실제 코드에서 확인해야 합니다.

현재 halil `EventMapper`에서는 Tool Call이 있는 Assistant message의 일반 `content`를 사용자 이벤트로 살리지 않고 Tool 이벤트 쪽만 반환하는 구조라서, 모델이:

```text
"먼저 프로젝트를 확인하겠습니다."
+
get_project_list()
```

를 함께 생성하더라도 **앞의 한국어 문장이 현재는 버려질 가능성이 있습니다.**

그래서 수정은 사실 크게 어렵지 않고:

```text
① 프롬프트
Tool 호출 전 사용자용 한국어 한 문장 생성

② Backend
그 content/commentary를 버리지 않고
agent_update 같은 이벤트로 전달

③ Frontend
지금 reasoning이 있던 자리에 agent_update 표시

④ reasoning.summary는 기본 화면에서 숨김
```

이면 됩니다.

**기존 디자인을 갈아엎을 필요도 없어요.**

---

그리고 혹시 담당자가 정말로:

> “아니, `reasoning.summary`라는 그 값 자체를 꼭 한국어로 만들고 싶은데?”

라고 하는 거라면 그때는 답이 달라집니다.

현재 기준 선택지는:

| 방법 | 가능 여부 | 판단 |
|---|---|---|
| `language="ko"` 같은 API 옵션 | ❌ 없음 | 불가 |
| 현재처럼 Prompt로 한국어 지시 | △ 이미 적용 중 | 실제로 영어 발생 |
| Prompt를 더 세게 쓰기 | △ 시도 가능 | 보장 못 함 |
| Reasoning Summary를 별도 번역 | ✅ 가능 | 추가 호출/지연 |
| **같은 호출의 Preamble/Commentary를 대신 표시** | **✅ 가능** | **가장 추천** |

그래서 지금 상황은 **“한국어로 만드는 방법이 없는 것”이 아니라, 한국어로 제어하기 어려운 `reasoning.summary`를 굳이 화면의 소스로 쓰고 있는 것**에 가깝습니다.

저라면 목요일 일정까지 감안해서도 **UI는 거의 그대로 두고 `reasoning.summary → user-visible Korean commentary/preamble`로 소스만 교체하는 방향**으로 갑니다. 이게 지금 발견된 문제에 대한 가장 직접적이고 구현 부담도 작은 대응책입니다. ([OpenAI Developers](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5&utm_source=chatgpt.com))