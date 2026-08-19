import { useEffect, useId, useRef, useState } from 'react';
import { Icon } from '../Icon/Icon';
import { ApiError } from '../../api/client';
import { deleteAvatar, fetchAvatarBlob, uploadAvatar } from '../../api/auth';
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
  // 올리거나 지운 뒤 다시 받아 오게 하는 값. 서버 주소가 같아서 이것 없이는
  // 바뀐 것을 알 방법이 없다.
  const [version, setVersion] = useState(0);
  /**
   * 받아 온 사진의 blob 주소.
   *
   * **주소를 그대로 `<img>` 에 넣으면 안 된다** — 이미지 요청에는 토큰이 안 실려
   * 401 이 나고, 화면은 사진이 있는데도 이름 첫 글자만 그린다(`fetchAvatarBlob`).
   * 못 받으면 `null` 로 두고 첫 글자로 되돌린다: 서버에는 있다는데 파일이 없는
   * 경우(저장소에서 사라졌거나 세션 만료)도 여기로 온다.
   */
  const [imageSrc, setImageSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !hasAvatar) {
      setImageSrc(null);
      return;
    }

    let dropped = false;
    let objectUrl: string | null = null;
    void fetchAvatarBlob(token).then((blob) => {
      if (dropped || !blob) return;
      objectUrl = URL.createObjectURL(blob);
      setImageSrc(objectUrl);
    });

    return () => {
      // 화면을 떠나거나 새 사진을 받으면 앞의 것을 반드시 놓아 준다 — 안 그러면
      // 바꿀 때마다 blob 이 메모리에 쌓인다.
      dropped = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, hasAvatar, version]);

  const showImage = Boolean(imageSrc);
  const initial = name.trim().slice(0, 1);

  async function handlePick(file: File | undefined) {
    if (!token || !file || busy) return;
    setBusy(true);
    try {
      await uploadAvatar(token, file);
      setVersion((prev) => prev + 1);
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
      setVersion((prev) => prev + 1);
      onChanged();
    } catch (error) {
      onError(error instanceof ApiError ? error.message : '사진을 삭제하지 못했습니다.');
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
          <img className={styles.image} src={imageSrc ?? ''} alt="" />
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
