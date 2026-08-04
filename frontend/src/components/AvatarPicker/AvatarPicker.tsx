import { useEffect, useId, useRef, useState } from 'react';
import { Icon } from '../Icon/Icon';
import { ApiError } from '../../api/client';
import { avatarUrl, deleteAvatar, uploadAvatar } from '../../api/auth';
import styles from './AvatarPicker.module.css';

export interface AvatarPickerProps {
  token: string | null;
  /** 사진이 없을 때 대신 그릴 이름. 첫 글자를 쓴다. */
  name: string;
  hasAvatar: boolean;
  /** 올리거나 지운 뒤. 부모가 프로필을 다시 읽어 `hasAvatar`를 갱신한다. */
  onChanged: () => void;
  onError: (message: string) => void;
}

/**
 * 프로필 사진. 눌러서 바꾸고, 올린 사진이 있으면 지울 수 있다.
 *
 * 형식·용량 안내와 삭제 버튼은 평소에 감춘다. 늘 떠 있으면 프로필에서 가장 눈에
 * 띄는 것이 제약 조건이 되는데, 그건 사진을 바꾸려는 순간에만 필요한 정보다.
 * 제약은 마우스를 올렸을 때 툴팁으로 보이고, 어겼을 때 오류로 알려준다.
 *
 * 사진이 없으면 이름 첫 글자를 그린다 — 사진을 담는 곳이 생기기 전부터 상단
 * 내비게이션이 쓰던 방식이라 화면 사이에서 같은 모양으로 보인다.
 */
export function AvatarPicker({ token, name, hasAvatar, onChanged, onError }: AvatarPickerProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  // 같은 URL로 새 사진이 올라오므로, 바뀐 것을 브라우저에 알리려면 값이 달라져야 한다.
  const [version, setVersion] = useState(() => Date.now());
  // 서버에는 있다는데 파일을 못 받는 경우가 있다(저장소에서 사라졌거나 세션 만료).
  // 깨진 이미지를 그리느니 이름 첫 글자로 되돌린다.
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [version, hasAvatar]);

  const showImage = hasAvatar && !imageFailed;
  const initial = name.trim().slice(0, 1);

  async function handlePick(file: File | undefined) {
    if (!token || !file || busy) return;
    setBusy(true);
    try {
      await uploadAvatar(token, file);
      setVersion(Date.now());
      onChanged();
    } catch (error) {
      onError(error instanceof ApiError ? error.message : '사진을 올리지 못했습니다.');
    } finally {
      setBusy(false);
      // 같은 파일을 다시 골랐을 때도 change 가 뜨도록 비운다.
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function handleRemove() {
    if (!token || busy) return;
    setBusy(true);
    try {
      await deleteAvatar(token);
      setVersion(Date.now());
      onChanged();
    } catch (error) {
      onError(error instanceof ApiError ? error.message : '사진을 지우지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.picker}>
      <label
        className={styles.surface}
        htmlFor={inputId}
        title="눌러서 프로필 사진 변경 · JPG, PNG, WEBP · 2MB 이하"
      >
        {showImage ? (
          <img
            className={styles.image}
            src={avatarUrl(version)}
            alt=""
            onError={() => setImageFailed(true)}
          />
        ) : (
          <span className={styles.initial} aria-hidden="true">
            {initial || <Icon name="user" size={22} color="var(--color-muted)" />}
          </span>
        )}
        <span className={styles.overlay} aria-hidden="true">
          <Icon name="refresh" size={16} color="#fff" spin={busy} />
        </span>
        <input
          id={inputId}
          ref={inputRef}
          className={styles.input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={busy}
          onChange={(event) => void handlePick(event.target.files?.[0])}
        />
      </label>

      {/* label 밖에 둔다 — 안에 넣으면 삭제를 눌러도 파일 선택창이 같이 열린다. */}
      {showImage && (
        <button
          type="button"
          className={styles.remove}
          onClick={handleRemove}
          disabled={busy}
          title="프로필 사진 삭제"
          aria-label="프로필 사진 삭제"
        >
          <Icon name="x" size={12} color="#fff" />
        </button>
      )}
    </div>
  );
}

export default AvatarPicker;
