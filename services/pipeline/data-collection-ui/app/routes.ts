import { index, prefix, route, type RouteConfig } from '@react-router/dev/routes'

export default [
  index('routes/index.tsx'),
  route('/collect', 'routes/data-collection/index.tsx'),
  route('/episodes', 'routes/episodes/index.tsx', [route(':episode_id', 'routes/episodes/episode/index.tsx')]),
  ...prefix('/api', [
    route('episode', 'routes/api/episode.ts'),
    route('teleop', 'routes/api/teleop.ts'),
    route('follower-reset', 'routes/api/follower-reset.ts'),
    route('record-start', 'routes/api/record-start.ts'),
    route('record-stop', 'routes/api/record-stop.ts'),
    route('review', 'routes/api/review.ts'),
    route('task', 'routes/api/task.ts'),
  ]),
] satisfies RouteConfig
