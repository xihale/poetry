<script setup lang="ts">
const { restore } = useLastRead()

// Client-only: read the stored reading position so the index can mark it.
onMounted(restore)
</script>

<template>
  <NuxtPage />
</template>

<style>
/* Page change: the new page rises into place from below. One direction for
   every navigation, matching the entrance; exiting only fades. */
.page-enter-active {
  transition: opacity 0.26s var(--ease), transform 0.26s var(--ease);
}

.page-leave-active {
  transition: opacity 0.15s ease-in;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
}
</style>
