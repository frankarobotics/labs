import { useFetcher } from 'react-router'

import Container from '@/components/Container'
import Separator from '@/components/Container/Separator'

import Button from '../Button'
import useDeleteFeedback from './useDeleteFeedback'

type DeleteEpisodeDialogProps = {
  ref: React.RefObject<HTMLDialogElement | null>
  id: string
}

export default function DeleteEpisodeDialog({ ref, id }: DeleteEpisodeDialogProps) {
  const fetcher = useFetcher()
  useDeleteFeedback(fetcher)
  return (
    <dialog
      className='absolute backdrop:bg-black/80 open:inset-0 open:h-full open:w-full open:bg-transparent'
      ref={ref}
    >
      <Container spacing='wide' className='absolute inset-0 m-auto h-fit max-w-128'>
        <span>Delete Episode</span>
        <Separator />
        Are you sure you want to delete Episode {id}? <strong>This action cannot be undone.</strong>
        <fetcher.Form
          method='post'
          action='/api/episode'
          className='screen:gap-3 flex w-full flex-row items-center justify-between gap-2'
          onSubmit={() => ref.current?.close()}
        >
          <input hidden name='_id' onChange={() => {}} value={id} />
          <Button type='button' variant='outline' onClick={() => ref.current?.close()}>
            Cancel
          </Button>
          <Button type='submit' name='_action' value='delete' variant='negative'>
            Delete
          </Button>
        </fetcher.Form>
      </Container>
    </dialog>
  )
}
