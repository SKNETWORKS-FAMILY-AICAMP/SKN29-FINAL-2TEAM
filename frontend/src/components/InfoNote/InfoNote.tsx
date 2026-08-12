import { useState } from 'react';
import type { ReactNode } from 'react';
import { Icon } from '../Icon/Icon';
import { Modal } from '../Modal/Modal';
import styles from './InfoNote.module.css';

/**
 * 제목 옆의 ⓘ. 누르면 설명이 모달로 열린다.
 *
 * **화면에 설명 문단을 깔지 않기 위한 자리다.** 우리는 「왜 이렇게 만들었는가」를
 * 화면 곳곳에 문단으로 적어 두었는데(Connector 탭·MCP 탭·Model 탭·프로젝트 상세…),
 * 그게 쌓이니 화면이 설명서처럼 보였다(2026-08-12 PM 지적). 알고 싶은 사람은
 * 누르고, 아는 사람은 안 누른다.
 *
 * **아무거나 여기 넣으면 안 된다.** 지금 상태를 알리는 것(「팀장만 연결할 수
 * 있습니다」·「본문이 아직 색인되지 않았습니다」·「승인 전까지 아무것도 등록되지
 * 않습니다」)은 사람이 지금 할 행동을 바꾸므로 화면에 그대로 남는다. 여기 담는
 * 것은 **몰라도 지금 행동이 바뀌지 않는 배경**뿐이다.
 */
export function InfoNote({
  title,
  children,
  label = '설명 보기',
}: {
  title: string;
  children: ReactNode;
  /** 스크린 리더가 읽을 이름. 아이콘만 있으므로 반드시 있어야 한다. */
  label?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" className={styles.trigger} aria-label={label} onClick={() => setOpen(true)}>
        <Icon name="info" size={15} color="var(--color-placeholder)" />
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={title} width={460}>
        <div className={styles.body}>{children}</div>
      </Modal>
    </>
  );
}
