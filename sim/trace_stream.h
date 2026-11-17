#ifndef SCPU_TRACE_STREAM_H
#define SCPU_TRACE_STREAM_H

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

// macOS <signal.h> defines sigemptyset as a macro (in addition to declaring
// the real function), which breaks the scope-qualified call below.
#if defined(sigemptyset)
#undef sigemptyset
#endif

// Dedicated diagnostic transport: fixed storage, explicit little-endian words,
// and FIFO-only output. A reader closing the pipe is normal cancellation.
class TraceStream {
public:
    static constexpr size_t RECORD_WORDS = 24;

    TraceStream() = default;
    TraceStream(const TraceStream&) = delete;
    TraceStream& operator=(const TraceStream&) = delete;
    ~TraceStream() {
        if (fd_ >= 0) ::close(fd_);
    }

    bool open_fifo(const char* path) {
        path_ = path;
        struct stat before;
        if (::lstat(path, &before) != 0) return fail("lstat", errno);
        if (!S_ISFIFO(before.st_mode)) return fail("stream path is not a FIFO", 0);
        struct sigaction action = {};
        action.sa_handler = SIG_IGN;
        if (::sigemptyset(&action.sa_mask) != 0 || ::sigaction(SIGPIPE, &action, nullptr) != 0) {
            return fail("ignore SIGPIPE", errno);
        }
        do {
            fd_ = ::open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
        } while (fd_ < 0 && errno == EINTR);
        if (fd_ < 0) return fail("open", errno);
        struct stat after;
        if (::fstat(fd_, &after) != 0) return fail("fstat", errno);
        if (!S_ISFIFO(after.st_mode) || before.st_dev != after.st_dev || before.st_ino != after.st_ino) {
            return fail("stream FIFO changed during open", 0);
        }
        const uint32_t header[] = {0x46534431U, 1U, RECORD_WORDS, 0U};
        return append_words(header, 4) && flush();
    }

    bool append_record(const uint32_t (&words)[RECORD_WORDS]) {
        return append_words(words, RECORD_WORDS);
    }

    bool finish() {
        const bool flushed = !failed_ && !cancelled_ && flush();
        if (fd_ >= 0) {
            const int fd = fd_;
            fd_ = -1;
            // Do not retry close(EINTR): Linux may already have released the fd.
            if (::close(fd) != 0 && !cancelled_) return fail("close", errno);
        }
        return flushed || cancelled_;
    }

    bool cancelled() const { return cancelled_; }

private:
    bool append_words(const uint32_t* words, size_t count) {
        if (failed_ || cancelled_) return false;
        const size_t bytes = count * 4;
        if (used_ + bytes > sizeof(buffer_) && !flush()) return false;
        for (size_t i = 0; i < count; ++i) {
            const uint32_t word = words[i];
            buffer_[used_++] = static_cast<unsigned char>(word);
            buffer_[used_++] = static_cast<unsigned char>(word >> 8);
            buffer_[used_++] = static_cast<unsigned char>(word >> 16);
            buffer_[used_++] = static_cast<unsigned char>(word >> 24);
        }
        return true;
    }

    bool flush() {
        size_t sent = 0;
        while (sent < used_) {
            const ssize_t count = ::write(fd_, buffer_ + sent, used_ - sent);
            if (count > 0) {
                sent += static_cast<size_t>(count);
            } else if (count < 0 && errno == EINTR) {
                continue;
            } else if (count < 0 && errno == EPIPE) {
                cancelled_ = true;
                used_ = 0;
                return false;
            } else {
                return fail("write", count < 0 ? errno : EIO);
            }
        }
        used_ = 0;
        return true;
    }

    bool fail(const char* operation, int error) {
        failed_ = true;
        std::fprintf(stderr, "trace stream %s: %s%s%s\n", path_ ? path_ : "", operation,
                     error ? ": " : "", error ? std::strerror(error) : "");
        return false;
    }

    int fd_ = -1;
    const char* path_ = nullptr;
    size_t used_ = 0;
    bool failed_ = false;
    bool cancelled_ = false;
    unsigned char buffer_[64 * 1024];
};

#endif
