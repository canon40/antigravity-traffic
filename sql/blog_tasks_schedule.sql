-- BlogTasks 스케줄 시드 (Agent-HQ / qkporqtajfikppwsishz)
-- Supabase SQL Editor 에서 실행

-- 1. 필요한 칸 추가 (이미 있으면 무시됨)
ALTER TABLE public."BlogTasks"
ADD COLUMN IF NOT EXISTS platform text,
ADD COLUMN IF NOT EXISTS scheduled_time timestamp with time zone,
ADD COLUMN IF NOT EXISTS account_id text;

-- 2. 기존 대기 데이터 정리
DELETE FROM public."BlogTasks" WHERE status = 'PENDING';

-- 3. 시간대별/계정별 데이터 입력
INSERT INTO public."BlogTasks" (topic, status, platform, account_id, scheduled_time)
VALUES
  -- [오전] Naver 1
  ('듀라코트 퍼마코트 자동차 유리막코팅제 - 폴리실라잔 9H 경도와 다이아몬드 코팅공법의 완성', 'PENDING', 'naver', 'hymini1', '2026-05-09 09:00:00'),
  ('오전 서로이웃 추가: 자동차 디테일링 및 바이크 라이더 타겟팅', 'PENDING', 'neighbor_action', 'hymini1', '2026-05-09 10:30:00'),

  -- [오후] Naver 2
  ('폭발적인 비딩과 쉬팅! 퍼마코트 초발수 코팅제로 관리하는 차량 도장면과 헬멧 실드', 'PENDING', 'naver', 'hymini11', '2026-05-09 14:00:00'),
  ('오후 서로이웃 추가: 셀프 세차 및 자동차 관리 커뮤니티 타겟팅', 'PENDING', 'neighbor_action', 'hymini11', '2026-05-09 15:30:00'),

  -- [저녁] Tstory
  ('듀라코트 리빙코트 - 욕실, 싱크대, 인덕션까지 전문가 포뮬러로 완성하는 홈케어 나노코팅', 'PENDING', 'tstory', 'hymini1@naver.com', '2026-05-09 20:00:00'),
  ('저녁 서로이웃 추가: 인테리어, 살림, 신축 입주 정보 관심사 타겟팅', 'PENDING', 'neighbor_action', 'hymini1', '2026-05-09 21:30:00');
