import { Link } from 'react-router-dom';
import { Logo } from '../../components';
import { PATHS } from '../../routes';
import styles from './PrivacyPage.module.css';

/**
 * 개인정보처리방침.
 *
 * **Google OAuth 앱을 게시하려고 만든 자리다**(2026-08-25). 게시 상태가
 * 「테스트 중」이면 **refresh token 이 7일 만에 만료돼서**, 매주 커넥터를 다시
 * 연결해야 한다 — 실서버 Drive 가 반복해서 만료되던 원인이 그것이었다.
 * 「프로덕션으로 게시」에 개인정보처리방침 URL 이 필수라 그 하나가 막고 있었다.
 *
 * **여기 적은 것은 전부 코드에서 확인한 사실이다.** 스코프는
 * `apps/connectors/oauth.py`, 저장하는 것은 `DB/schema.sql` 의 `doc`·`chunk`·
 * `vec_idx`, 외부로 나가는 곳은 `services/agent_runtime/models/factory.py`
 * (OpenAI·Anthropic), `services/document_pipeline/runpod_client.py`(RunPod),
 * `services/websearch/client.py`(Tavily)를 보고 적었다. 지어낸 문장이 없다.
 *
 * **상용 서비스가 아니라는 것을 숨기지 않는다.** 교육 과정의 졸업 프로젝트라고
 * 먼저 밝히는 편이 정확하고, 지키지 못할 약속(보안 인증·SLA 같은 것)을 쓰지
 * 않아도 된다.
 *
 * 로그인 없이 열려야 한다 — Google 이 심사에서 이 주소를 직접 연다.
 */

const UPDATED_AT = '2026년 8월 25일';

export default function PrivacyPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to={PATHS.landing} className={styles.brand} aria-label="halil 홈으로">
          <Logo />
        </Link>
      </header>

      <main className={styles.body}>
        <h1 className={styles.title}>개인정보처리방침</h1>
        <p className={styles.updated}>최종 수정일 · {UPDATED_AT}</p>

        <section className={styles.notice}>
          <p>
            <strong>halil 은 교육 과정에서 만든 졸업 프로젝트입니다.</strong> 상용 서비스가 아니며,
            평가와 시연을 위해 운영됩니다. 실제 업무 데이터를 연결하기 전에 이 점을 고려해 주세요.
          </p>
        </section>

        <h2>1. 무엇을 수집하나요</h2>
        <p>halil 은 사용자가 직접 연결한 곳에서만 데이터를 가져옵니다.</p>
        <ul>
          <li>
            <strong>계정 정보</strong> — 이메일, 표시 이름, 비밀번호(단방향 암호화하여 저장하며 원문은
            보관하지 않습니다).
          </li>
          <li>
            <strong>문서 저장소(Google Drive)</strong> — 팀장이 지정한 폴더 안의 문서와 그 메타데이터.
            요청하는 권한은 <code>drive.readonly</code>, <code>drive.metadata.readonly</code> 로{' '}
            <strong>읽기 전용</strong>입니다. halil 은 Drive 의 파일을 수정하거나 삭제하지 않습니다.
          </li>
          <li>
            <strong>업무 기록소(Jira)</strong> — 이슈의 제목·담당자·상태·공수·마감일. 권한은{' '}
            <code>read:jira-work</code>, <code>read:jira-user</code>, <code>write:jira-work</code> 입니다.
            쓰기 권한은 <strong>사용자가 화면에서 승인한 업무를 이슈로 등록할 때만</strong> 쓰입니다.
          </li>
          <li>
            <strong>인사 정보</strong> — 이름, 소속 조직, 직책, 보유 기술. 업무 배분과 부하 계산에
            쓰입니다.
          </li>
          <li>
            <strong>사용자가 직접 올린 파일</strong> — 「문서 &gt; 내 파일」에 업로드한 문서.
          </li>
        </ul>

        <h2>2. 어떻게 쓰나요</h2>
        <p>
          가져온 문서는 본문을 잘라 <strong>검색용 수치(임베딩)</strong> 로 바꿔 저장합니다. 사용자가
          질문하면 그 수치로 관련 문장을 찾아 답의 근거로 씁니다. 답에는 어느 문서에서 왔는지가 함께
          표시됩니다.
        </p>
        <p>
          <strong>문서 저장소에서 가져온 파일의 원본은 읽고 나면 지웁니다.</strong> 읽는 동안만 사본을
          두고, 검색용 수치를 만든 뒤에는 지웁니다. 원본은 Google Drive 에 그대로 있고, 다시 읽어야 할
          때 그때 다시 가져옵니다. 「문서 &gt; 내 파일」에 직접 올린 파일은 다릅니다 — 그쪽은 원본이
          halil 에만 있어서 사용자가 지울 때까지 보관합니다.
        </p>
        <p>
          <strong>수집한 데이터로 AI 모델을 학습시키지 않습니다.</strong>
        </p>

        <h2>3. 어디에 보관하나요</h2>
        <p>
          Amazon Web Services(서울 리전)에 보관합니다. 외부 서비스 접근에 쓰는 인증 정보는 암호화하여
          저장합니다.
        </p>

        <h2>4. 외부로 전달되는 것</h2>
        <p>기능을 제공하기 위해 아래 서비스에 데이터가 전달됩니다.</p>
        <ul>
          <li>
            <strong>OpenAI · Anthropic</strong> — 질문과 근거 문장을 보내 답을 생성합니다.
          </li>
          <li>
            <strong>RunPod</strong> — 문서 본문을 읽어 임베딩을 만듭니다.
          </li>
          <li>
            <strong>Tavily</strong> — 사용자가 웹 검색을 요청했을 때 그 검색어를 보냅니다.
          </li>
        </ul>
        <p>이 밖에 개인정보를 제3자에게 판매하거나 제공하지 않습니다.</p>

        <h2>5. 누가 볼 수 있나요</h2>
        <p>
          데이터는 <strong>팀 단위로 격리</strong>됩니다. 다른 팀의 문서나 업무는 검색되지 않습니다.
          「내 파일」에 올린 문서는 기본적으로 본인만 사용하며, 직접 「팀에 공유」를 켠 경우에만 팀원이
          볼 수 있습니다.
        </p>

        <h2>6. 얼마나 보관하나요</h2>
        <ul>
          <li>
            문서 저장소에서 가져온 파일의 원본은 <strong>읽고 나면 곧바로 지웁니다.</strong> 검색용
            수치만 남습니다.
          </li>
          <li>직접 올린 파일은 삭제하면 원본과 검색용 수치가 함께 삭제됩니다.</li>
          <li>프로젝트를 삭제하면 그 프로젝트가 읽어온 업무가 함께 삭제됩니다.</li>
          <li>커넥터 연결을 해제하면 저장된 인증 정보가 삭제됩니다.</li>
          <li>
            <strong>프로젝트 운영이 끝나면 데이터베이스와 저장소를 모두 폐기합니다.</strong>
          </li>
        </ul>

        <h2>7. 연결을 끊고 싶다면</h2>
        <p>
          halil 안에서는 「설정 &gt; 커넥터」에서 연결을 해제할 수 있습니다. Google 계정 쪽에서 직접
          철회하려면{' '}
          <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer noopener">
            Google 계정 &gt; 타사 앱 및 서비스
          </a>{' '}
          에서 halil 의 접근 권한을 삭제하면 됩니다.
        </p>

        <h2>8. 문의</h2>
        <p>
          개인정보와 관련한 문의는 <a href="mailto:true.j11@gmail.com">true.j11@gmail.com</a> 으로
          보내 주세요.
        </p>

        <p className={styles.footer}>
          <Link to={PATHS.landing}>halil 홈으로</Link>
        </p>
      </main>
    </div>
  );
}
